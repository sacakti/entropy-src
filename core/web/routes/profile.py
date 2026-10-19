"""
Current user's profile API: display name, email and profile picture.
"""

from __future__ import annotations

import io
import re
from typing import Optional, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict, Field

from core.web.routes.auth import _current_session, verify_csrf
from lib.database.repositories.user_web_settings import UserWebSettingsRepository
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/profile", tags=["profile"])

SessionRecord = Tuple[Session, str, User]

AVATAR_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
AVATAR_SIZE = 512

# Deliberately loose: the address only needs to look like one.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=254)


def _repository(request: Request) -> UserWebSettingsRepository:
    context = request.app.state.entropy_context

    if context.database_manager is None:
        raise HTTPException(status_code=500, detail="Database is unavailable.")

    return UserWebSettingsRepository(context.database_manager.connection)


def _payload(user: User, avatar_version: Optional[str]) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "avatar_url": (
            f"/api/profile/avatar?v={avatar_version}" if avatar_version else None
        ),
    }


@router.get("")
def get_profile(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """Return the signed-in user's profile."""

    _, _, user = record
    assert user.id is not None

    response.headers["Cache-Control"] = "no-store"

    return _payload(user, _repository(request).avatar_version(user.id))


@router.patch("", dependencies=[Depends(verify_csrf)])
def update_profile(
    payload: ProfileUpdate,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """Update the signed-in user's display name and email."""

    _, _, user = record
    assert user.id is not None

    full_name = (payload.full_name or "").strip() or None
    email = (payload.email or "").strip() or None

    if email is not None and not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")

    stored = request.app.state.entropy_context.user_manager.update_profile(
        user,
        full_name,
        email,
    )

    # The session keeps its own copy of the user; keep it current.
    user.full_name = stored.full_name
    user.email = stored.email

    response.headers["Cache-Control"] = "no-store"

    return _payload(user, _repository(request).avatar_version(user.id))


@router.get("/avatar")
def get_avatar(
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """Return the signed-in user's profile picture."""

    _, _, user = record
    assert user.id is not None

    avatar = _repository(request).get_avatar(user.id)

    if avatar is None:
        raise HTTPException(status_code=404, detail="No profile picture.")

    mime_type, data, _ = avatar

    # URLs carry the update time, so a cached copy is never stale.
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.put("/avatar", dependencies=[Depends(verify_csrf)])
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """Set the profile picture from an uploaded JPEG, PNG or WebP image."""

    from PIL import Image, ImageOps

    _, _, user = record
    assert user.id is not None

    data = await file.read(AVATAR_MAX_UPLOAD_BYTES + 1)

    if not data:
        raise HTTPException(status_code=400, detail="Choose an image to upload.")

    if len(data) > AVATAR_MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Images must not exceed 10 MB.")

    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ("JPEG", "PNG", "WEBP"):
                raise HTTPException(
                    status_code=400,
                    detail="Only JPEG, PNG and WebP images are supported.",
                )

            # Re-encode a square crop: strips metadata and bounds the size.
            image = ImageOps.exif_transpose(image)
            image = ImageOps.fit(
                image.convert("RGBA"),
                (AVATAR_SIZE, AVATAR_SIZE),
            )

            output = io.BytesIO()

            if image.getextrema()[3][0] < 255:
                image.save(output, format="PNG", optimize=True)
                mime_type = "image/png"
            else:
                image.convert("RGB").save(output, format="JPEG", quality=88)
                mime_type = "image/jpeg"
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a valid image.",
        ) from exc

    repository = _repository(request)
    repository.set_avatar(user.id, mime_type, output.getvalue())

    return _payload(user, repository.avatar_version(user.id))


@router.delete("/avatar", dependencies=[Depends(verify_csrf)])
def delete_avatar(
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """Remove the profile picture."""

    _, _, user = record
    assert user.id is not None

    _repository(request).delete_avatar(user.id)

    return _payload(user, None)
