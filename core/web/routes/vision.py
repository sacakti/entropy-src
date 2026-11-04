"""
Vision: whether it is on and the messages for everyone (any signed-in user reads these),
and sending or ending those messages (system.settings).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import current_project, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.session import Session
from lib.models.users import User
from lib.system.settings import SystemSettings
from lib.vision.broadcasts import BroadcastError, BroadcastStore

router = APIRouter(prefix="/api/vision", tags=["vision"])

SessionRecord = tuple[str, Session, User]


class BroadcastRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    level: str = "info"
    duration_minutes: int = 60


def _connection(request: Request) -> Any:
    return request.app.state.entropy_context.database_manager.connection


def _enabled(request: Request) -> bool:
    # Only a plain value is read, so no vault key is needed (every open page polls this).
    return bool(SystemSettings(_connection(request)).get("vision")["enabled"])


def _database_switch() -> Optional[Dict[str, Any]]:
    """A database switch under way, which everyone must know about: no changes are saved."""

    from lib.database.switch import ACTIVE_STATES, PROGRESS

    progress = PROGRESS.snapshot()
    if progress["state"] not in ACTIVE_STATES:
        return None
    return {key: value for key, value in progress.items() if key != "error"}


def _public(broadcast: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in broadcast.items() if key != "ended_at"}


def _project_activity(request: Request, user: User) -> bool:
    """Whether the current project shows its members each other's runs."""

    try:
        project = current_project(request, user)
    except HTTPException:
        # No access to the project asked for: nothing of it to show anyway.
        return False
    return bool(project and project.get("vision_activity", True))


@router.get("")
def vision_status(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """Whether Vision is on, and the messages everyone should see."""

    response.headers["Cache-Control"] = "no-store"
    if not _enabled(request):
        return {"enabled": False, "broadcasts": [], "project_activity": False}
    return {
        "enabled": True,
        "project_activity": _project_activity(request, record[2]),
        "broadcasts": [_public(item) for item in BroadcastStore(_connection(request)).active()],
        "database_switch": _database_switch(),
    }


@router.post("/broadcasts", status_code=201, dependencies=[Depends(verify_csrf)])
def send_broadcast(
    payload: BroadcastRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """Send a message to everyone."""

    _, _, user = record
    require(request, user, "system.settings")
    if not _enabled(request):
        raise HTTPException(status_code=409, detail="Vision is off: turn it on to send a message.")
    try:
        broadcast = BroadcastStore(_connection(request)).create(
            payload.message, payload.level, user.username, payload.duration_minutes
        )
    except BroadcastError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return _public(broadcast)


@router.delete("/broadcasts/{broadcast_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def end_broadcast(
    broadcast_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> None:
    """Stop showing a message to everyone."""

    _, _, user = record
    require(request, user, "system.settings")
    if not BroadcastStore(_connection(request)).end(broadcast_id):
        raise HTTPException(status_code=404, detail="That message is not active.")
