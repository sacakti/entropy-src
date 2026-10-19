"""
Background images API.
"""

from __future__ import annotations

import datetime
import io
import re
import zipfile
from typing import Optional, Tuple
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
from PIL import Image

from lib.models.session import Session
from lib.models.users import User

from core.web.routes.auth import _current_session, verify_csrf


router = APIRouter(
    prefix="/api/backgrounds",
    tags=["backgrounds"],
)

SessionRecord = Tuple[Session, str, User]

IMAGE_MAX_BYTES = 20 * 1024 * 1024
VIDEO_MAX_BYTES = 100 * 1024 * 1024

IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/webm": "webm",
}

RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


def _video_mime_type(data: bytes) -> Optional[str]:
    """Identify MP4 and WebM files by their signatures."""

    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"

    if data[:4] == b"\x1a\x45\xdf\xa3" and b"webm" in data[:64]:
        return "video/webm"

    return None


def _clear_deleted_selection(connection, user_id: int) -> None:
    """Unset the user's background when it no longer exists."""

    connection.execute(
        """
        UPDATE user_preferences
        SET background_image_id = NULL
        WHERE user_id = ?
          AND background_image_id IS NOT NULL
          AND background_image_id NOT IN (SELECT id FROM background_images)
        """,
        (user_id,),
    )


def _connection(request: Request):
    """Return the active database connection."""

    context = request.app.state.entropy_context

    if context.database_manager is None:
        raise HTTPException(
            status_code=500,
            detail="Database is unavailable.",
        )

    return context.database_manager.connection


def _seed_builtins(connection) -> None:
    """Add built-ins shipped after the install's migration (e.g. videos)."""

    if getattr(connection, "_entropy_backgrounds_seeded", False):
        return

    from pathlib import Path

    from lib.database.seeders.background_images import BackgroundImagesSeeder

    try:
        BackgroundImagesSeeder(
            Path(__file__).resolve().parents[3] / "lib" / "assets" / "backgrounds"
        ).seed(connection)
    finally:
        setattr(connection, "_entropy_backgrounds_seeded", True)


@router.get("")
def list_backgrounds(
    request: Request,
    response: Response,
    session_record: SessionRecord = Depends(_current_session),
) -> list[dict]:
    """List built-in and current-user background images."""

    session, _, _ = session_record
    connection = _connection(request)

    _seed_builtins(connection)

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

@router.post("", dependencies=[Depends(verify_csrf)])
async def upload_background(
    request: Request,
    file: UploadFile = File(...),
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    """Upload a background image or video for the current user."""

    session, _, _ = session_record

    image_data = await file.read(VIDEO_MAX_BYTES + 1)

    if not image_data:
        raise HTTPException(
            status_code=400,
            detail="Please select an image or video to upload.",
        )

    mime_type = _video_mime_type(image_data)

    if mime_type is not None:
        if len(image_data) > VIDEO_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Videos must not exceed 100 MB.",
            )
    else:
        if len(image_data) > IMAGE_MAX_BYTES:
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
                detail=(
                    "Upload a JPEG, PNG or WebP image, or an MP4 or WebM video."
                ),
            ) from exc

        if image_format not in IMAGE_FORMATS:
            raise HTTPException(
                status_code=400,
                detail="Only JPEG, PNG, and WebP images are supported.",
            )

        mime_type = IMAGE_FORMATS[image_format]

    # Use a safe, user-facing name rather than trusting the file path.
    filename = (file.filename or "Background").replace("\\", "/")
    name = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0].strip()
    name = name[:100] or "Background"

    connection = _connection(request)

    image_key = f"user-{session.user_id}-{uuid4().hex}"

    with connection.transaction():
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

@router.get("/archive")
def download_uploads(
    request: Request,
    session_record: SessionRecord = Depends(_current_session),
) -> Response:
    """Return every background the user uploaded as one zip archive."""

    session, _, _ = session_record
    connection = _connection(request)

    rows = connection.fetchall(
        """
        SELECT id, name, mime_type, image_data
        FROM background_images
        WHERE owner_user_id = ?
          AND source = 'upload'
        ORDER BY name, id
        """,
        (session.user_id,),
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="You have not uploaded any backgrounds.",
        )

    buffer = io.BytesIO()
    used = set()

    # Images and videos are already compressed.
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for row in rows:
            stem = re.sub(r"[^\w.-]+", "_", row["name"]).strip("._") or "background"
            extension = EXTENSIONS.get(row["mime_type"], "bin")
            filename = f"{stem}.{extension}"

            if filename in used:
                filename = f"{stem}-{row['id']}.{extension}"

            used.add(filename)
            archive.writestr(filename, bytes(row["image_data"]))

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="entropy-backgrounds.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("", dependencies=[Depends(verify_csrf)])
def delete_uploads(
    request: Request,
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    """Delete every background the user uploaded; built-ins are kept."""

    session, _, _ = session_record
    connection = _connection(request)

    with connection.transaction():
        cursor = connection.execute(
            """
            DELETE FROM background_images
            WHERE owner_user_id = ?
              AND source = 'upload'
            """,
            (session.user_id,),
        )
        deleted = cursor.rowcount

        _clear_deleted_selection(connection, session.user_id)

    return {
        "deleted": deleted,
        "message": f"Deleted {deleted} uploaded background{'s' if deleted != 1 else ''}.",
    }


@router.get("/{image_id}/image")
def get_background_image(
    image_id: int,
    request: Request,
    session_record: SessionRecord = Depends(_current_session),
) -> Response:
    """Return image or video bytes visible to the user; honours Range."""

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

    data = bytes(row["image_data"])
    size = len(data)
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff",
    }

    # Browsers (Safari in particular) stream video with byte ranges.
    match = RANGE_PATTERN.match(request.headers.get("range", "").strip())

    if match and (match.group(1) or match.group(2)):
        first, last = match.groups()

        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            start = max(size - int(last), 0)
            end = size - 1

        if start >= size or start > end:
            return Response(
                status_code=416,
                headers={**headers, "Content-Range": f"bytes */{size}"},
            )

        return Response(
            content=data[start : end + 1],
            status_code=206,
            media_type=row["mime_type"],
            headers={**headers, "Content-Range": f"bytes {start}-{end}/{size}"},
        )

    return Response(
        content=data,
        media_type=row["mime_type"],
        headers=headers,
    )

@router.delete("/{image_id}", dependencies=[Depends(verify_csrf)])
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

    with connection.transaction():
        connection.execute(
            """
            DELETE FROM background_images
            WHERE id = ?
              AND owner_user_id = ?
              AND source = 'upload'
            """,
            (image_id, session.user_id),
        )

        _clear_deleted_selection(connection, session.user_id)

    return {"message": "Background image deleted successfully."}
