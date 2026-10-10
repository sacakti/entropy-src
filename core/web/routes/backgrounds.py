"""
Background images API.
"""

from __future__ import annotations

import datetime
from typing import Tuple
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
import io
from PIL import Image

from lib.models.session import Session
from lib.models.users import User

from core.web.routes.auth import _current_session


router = APIRouter(
    prefix="/api/backgrounds",
    tags=["backgrounds"],
)

SessionRecord = Tuple[Session, str, User]


def _connection(request: Request):
    """Return the active database connection."""

    context = request.app.state.entropy_context

    if context.database_manager is None:
        raise HTTPException(
            status_code=500,
            detail="Database is unavailable.",
        )

    return context.database_manager.connection


@router.get("")
def list_backgrounds(
    request: Request,
    response: Response,
    session_record: SessionRecord = Depends(_current_session),
) -> list[dict]:
    """List built-in and current-user background images."""

    session, _, _ = session_record
    connection = _connection(request)

    rows = connection.fetchall(
        """
        SELECT
            id,
            name,
            mime_type,
            size_bytes,
            source
        FROM background_images
        WHERE source = 'builtin'
           OR owner_user_id = ?
        ORDER BY source, name
        """,
        (session.user_id,),
    )

    response.headers["Cache-Control"] = "no-store"

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "mime_type": row["mime_type"],
            "size_bytes": row["size_bytes"],
            "source": row["source"],
            "url": f"/api/backgrounds/{row['id']}/image",
        }
        for row in rows
    ]

@router.post("")
async def upload_background(
    request: Request,
    file: UploadFile = File(...),
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    """Upload a background image for the current user."""

    session, _, _ = session_record

    allowed_formats = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }
    max_size_bytes = 20 * 1024 * 1024

    image_data = await file.read(max_size_bytes + 1)

    if not image_data:
        raise HTTPException(
            status_code=400,
            detail="Please select an image to upload.",
        )

    if len(image_data) > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail="Image size must not exceed 20 MB.",
        )

    try:
        with Image.open(io.BytesIO(image_data)) as image:
            image_format = image.format
            image.verify()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a valid supported image.",
        ) from exc

    if image_format not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail="Only JPEG, PNG, and WebP images are supported.",
        )

    mime_type = allowed_formats[image_format]

    # Use a safe, user-facing name rather than trusting the file path.
    filename = (file.filename or "Background").replace("\\", "/")
    name = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0].strip()
    name = name[:100] or "Background"

    connection = _connection(request)

    image_key = f"user-{session.user_id}-{uuid4().hex}"

    connection.execute(
        """
        INSERT INTO background_images (
            image_key,
            owner_user_id,
            name,
            mime_type,
            size_bytes,
            image_data,
            source,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'upload', ?)
        """,
        (
            image_key,
            session.user_id,
            name,
            mime_type,
            len(image_data),
            image_data,
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )

    row = connection.fetchone(
        """
        SELECT id, name, mime_type, size_bytes, source
        FROM background_images
        WHERE image_key = ?
          AND owner_user_id = ?
        LIMIT 1
        """,
        (image_key, session.user_id),
    )

    if row is None:
        raise HTTPException(
            status_code=500,
            detail="Background image was uploaded but could not be retrieved.",
        )

    return {
        "id": row["id"],
        "name": row["name"],
        "mime_type": row["mime_type"],
        "size_bytes": row["size_bytes"],
        "source": row["source"],
        "url": f"/api/backgrounds/{row['id']}/image",
    }

@router.get("/{image_id}/image")
def get_background_image(
    image_id: int,
    request: Request,
    response: Response,
    session_record: SessionRecord = Depends(_current_session),
) -> Response:
    """Return image bytes when the image is visible to the user."""

    session, _, _ = session_record
    connection = _connection(request)

    row = connection.fetchone(
        """
        SELECT mime_type, image_data
        FROM background_images
        WHERE id = ?
          AND (
                source = 'builtin'
                OR owner_user_id = ?
          )
        LIMIT 1
        """,
        (
            image_id,
            session.user_id,
        ),
    )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Background image not found.",
        )

    response.headers["Cache-Control"] = "private, max-age=300"
    response.headers["X-Content-Type-Options"] = "nosniff"

    return Response(
        content=row["image_data"],
        media_type=row["mime_type"],
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )

@router.delete("/{image_id}")
def delete_background(
    image_id: int,
    request: Request,
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    """Delete a background image owned by the current user."""

    session, _, _ = session_record
    connection = _connection(request)

    row = connection.fetchone(
        """
        SELECT id
        FROM background_images
        WHERE id = ?
          AND owner_user_id = ?
          AND source = 'upload'
        LIMIT 1
        """,
        (image_id, session.user_id),
    )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Uploaded background not found.",
        )

    connection.execute(
        """
        DELETE FROM background_images
        WHERE id = ?
          AND owner_user_id = ?
          AND source = 'upload'
        """,
        (image_id, session.user_id),
    )

    return {"message": "Background image deleted successfully."}
