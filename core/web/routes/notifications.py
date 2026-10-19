"""
Notification center API for the signed-in user.
"""

from __future__ import annotations

from typing import Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from core.web.routes.auth import _current_session, verify_csrf
from lib.database.repositories.notifications import NotificationRepository
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

SessionRecord = Tuple[Session, str, User]


class NotificationCreate(BaseModel):
    """A notification the browser records for its own user (e.g. upload done)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=2000)
    level: Literal["info", "success", "warning", "error"] = "info"
    source: Optional[str] = Field(default=None, max_length=40)


def _repository(request: Request) -> NotificationRepository:
    context = request.app.state.entropy_context

    if context is None or context.database_manager is None:
        raise HTTPException(status_code=503, detail="Database is unavailable.")

    return NotificationRepository(context.database_manager.connection)


def _user_id(record: SessionRecord) -> int:
    _, _, user = record
    assert user.id is not None
    return user.id


@router.get("")
def list_notifications(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    record: SessionRecord = Depends(_current_session),
) -> dict:
    repository = _repository(request)
    user_id = _user_id(record)

    response.headers["Cache-Control"] = "no-store"

    return {
        "items": repository.list(user_id, limit),
        "unread": repository.unread_count(user_id),
    }


@router.post("", status_code=201, dependencies=[Depends(verify_csrf)])
def create_notification(
    payload: NotificationCreate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    return _repository(request).create(
        _user_id(record),
        payload.title.strip(),
        payload.message.strip(),
        payload.level,
        payload.source,
    )


@router.post("/read", dependencies=[Depends(verify_csrf)])
def mark_all_read(
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    return {"updated": _repository(request).mark_read(_user_id(record))}


@router.post("/{notification_id}/read", dependencies=[Depends(verify_csrf)])
def mark_read(
    notification_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    if not _repository(request).mark_read(_user_id(record), notification_id):
        raise HTTPException(status_code=404, detail="Notification not found.")

    return {"updated": 1}


@router.delete("", dependencies=[Depends(verify_csrf)])
def clear_notifications(
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    return {"deleted": _repository(request).delete(_user_id(record))}


@router.delete("/{notification_id}", dependencies=[Depends(verify_csrf)])
def delete_notification(
    notification_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    if not _repository(request).delete(_user_id(record), notification_id):
        raise HTTPException(status_code=404, detail="Notification not found.")

    return {"deleted": 1}
