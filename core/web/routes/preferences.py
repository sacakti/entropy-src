"""
User preferences API.
"""

from __future__ import annotations

import re
from typing import Dict, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.routes.auth import _current_session, verify_csrf
from lib.database.repositories.user_preferences import (
    UserPreferencesRepository,
)
from lib.database.repositories.user_web_settings import (
    UserWebSettingsRepository,
)
from lib.models.session import Session
from lib.models.users import User


router = APIRouter(
    prefix="/api/preferences",
    tags=["preferences"],
)

SessionRecord = Tuple[Session, str, User]



class PreferencesUpdate(BaseModel):
    """Preferences update request."""

    theme: Literal["dark", "light"]
    accent_color: str
    background_image_id: Optional[int] = None
    background_fit: Literal["cover", "contain", "fill"] = "cover"
    background_opacity: int = Field(default=35, ge=0, le=100)
    modal_backdrop_opacity: int = Field(default=48, ge=0, le=80)

    @classmethod
    def validate_opacity(cls, value: int) -> int:
        if not 0 <= value <= 100:
            raise ValueError("background_opacity must be between 0 and 100.")
        return value



def _repository(
    request: Request,
) -> UserPreferencesRepository:
    """
    Return the user preferences repository.
    """

    context = request.app.state.entropy_context

    if context.database_manager is None:
        raise HTTPException(
            status_code=500,
            detail="Database is unavailable.",
        )

    return UserPreferencesRepository(
        context.database_manager.connection,
    )


@router.get("")
def get_preferences(
    request: Request,
    response: Response,
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    """
    Return preferences for the authenticated user.
    """

    session, _, _ = session_record

    response.headers["Cache-Control"] = "no-store"

    repository = _repository(
        request,
    )

    return repository.get(
        session.user_id,
    )


@router.put(
    "",
    dependencies=[Depends(verify_csrf)],
)
def update_preferences(
    payload: PreferencesUpdate,
    request: Request,
    response: Response,
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    """
    Update preferences for the authenticated user.
    """

    session, _, _ = session_record

    if re.fullmatch(
        r"#[0-9a-fA-F]{6}",
        payload.accent_color,
    ) is None:
        raise HTTPException(
            status_code=422,
            detail="accent_color must be a six-digit hexadecimal color.",
        )

    context = request.app.state.entropy_context

    if context.database_manager is None:
        raise HTTPException(
            status_code=500,
            detail="Database is unavailable.",
        )

    connection = context.database_manager.connection

    # A selected image must be built-in or owned by this user.
    if payload.background_image_id is not None:
        image = connection.fetchone(
            """
            SELECT 1
            FROM background_images
            WHERE id = ?
              AND (
                    source = 'builtin'
                    OR owner_user_id = ?
              )
            LIMIT 1
            """,
            (
                payload.background_image_id,
                session.user_id,
            ),
        )

        if image is None:
            raise HTTPException(
                status_code=422,
                detail="Background image was not found or is not accessible.",
            )

    repository = UserPreferencesRepository(
        connection,
    )

    response.headers["Cache-Control"] = "no-store"

    return repository.update(
        user_id=session.user_id,
        theme=payload.theme,
        accent_color=payload.accent_color,
        background_image_id=payload.background_image_id,
        background_fit=payload.background_fit,
        background_opacity=payload.background_opacity,
        modal_backdrop_opacity=payload.modal_backdrop_opacity,
    )


# ----------------------------------------------------------------------
# Wallpaper placement and shuffle
# ----------------------------------------------------------------------


class WallpaperPlacement(BaseModel):
    """Where a wallpaper sits: focal point in percent and zoom in percent."""

    x: float = Field(default=50, ge=0, le=100)
    y: float = Field(default=50, ge=0, le=100)
    zoom: float = Field(default=100, ge=100, le=400)


class WallpaperShuffle(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=15, ge=1, le=1440)
    source: Literal["all", "uploads"] = "all"


class WallpaperSettings(BaseModel):
    # Keyed by background id; images without an entry fit automatically.
    placements: Dict[str, WallpaperPlacement] = Field(default_factory=dict)
    shuffle: WallpaperShuffle = Field(default_factory=WallpaperShuffle)


def _wallpaper_repository(request: Request) -> UserWebSettingsRepository:
    context = request.app.state.entropy_context

    if context.database_manager is None:
        raise HTTPException(status_code=500, detail="Database is unavailable.")

    return UserWebSettingsRepository(context.database_manager.connection)


def _wallpaper(settings: dict) -> dict:
    try:
        return WallpaperSettings(**settings.get("wallpaper", {})).model_dump()
    except ValueError:
        return WallpaperSettings().model_dump()


@router.get("/wallpaper")
def get_wallpaper_settings(
    request: Request,
    response: Response,
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    """Return wallpaper placements and shuffle settings."""

    session, _, _ = session_record
    response.headers["Cache-Control"] = "no-store"

    return _wallpaper(_wallpaper_repository(request).get_settings(session.user_id))


@router.put("/wallpaper", dependencies=[Depends(verify_csrf)])
def update_wallpaper_settings(
    payload: WallpaperSettings,
    request: Request,
    response: Response,
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    """Replace wallpaper placements and shuffle settings."""

    session, _, _ = session_record
    response.headers["Cache-Control"] = "no-store"

    if len(payload.placements) > 500:
        raise HTTPException(status_code=422, detail="Too many wallpaper placements.")

    settings = _wallpaper_repository(request).update_settings(
        session.user_id,
        {"wallpaper": payload.model_dump()},
    )

    return _wallpaper(settings)


# ----------------------------------------------------------------------
# Interface style
# ----------------------------------------------------------------------


class InterfaceSettings(BaseModel):
    # Translucent "liquid glass" buttons, dialogs and menus.
    glass: bool = False


def _interface(settings: dict) -> dict:
    try:
        return InterfaceSettings(**settings.get("interface", {})).model_dump()
    except ValueError:
        return InterfaceSettings().model_dump()


@router.get("/interface")
def get_interface_settings(
    request: Request,
    response: Response,
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    session, _, _ = session_record
    response.headers["Cache-Control"] = "no-store"

    return _interface(_wallpaper_repository(request).get_settings(session.user_id))


@router.put("/interface", dependencies=[Depends(verify_csrf)])
def update_interface_settings(
    payload: InterfaceSettings,
    request: Request,
    response: Response,
    session_record: SessionRecord = Depends(_current_session),
) -> dict:
    session, _, _ = session_record
    response.headers["Cache-Control"] = "no-store"

    settings = _wallpaper_repository(request).update_settings(
        session.user_id,
        {"interface": payload.model_dump()},
    )

    return _interface(settings)
