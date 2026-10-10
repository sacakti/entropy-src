"""
User preferences API.
"""

from __future__ import annotations

import re
from typing import Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.routes.auth import _current_session, verify_csrf
from lib.database.repositories.user_preferences import (
    UserPreferencesRepository,
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
    )
