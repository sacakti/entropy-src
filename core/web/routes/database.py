"""
Administration -> Settings -> Database: the state of entropy.db, its guard
and backups; backing up now, checking it, and where backups go.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.web.projects import require
from core.web.routes.auth import _current_session, verify_csrf
from lib.database.safety import DatabaseSafetyError, check_file
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/admin/database", tags=["administration"])

SessionRecord = Tuple[Session, str, User]


class SafetySettings(BaseModel):
    backup_dir: Optional[str] = Field(default=None, max_length=4096)
    interval_hours: Optional[float] = None
    keep: Optional[int] = None


def _safety(request: Request, record: SessionRecord) -> Any:
    require(request, record[2], "system.settings")
    manager = getattr(request.app.state.entropy_context, "database_manager", None)
    safety = getattr(manager, "safety", None)
    if safety is None:
        raise HTTPException(status_code=503, detail="Database safety is unavailable.")
    return safety


@router.get("")
def status(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    safety = _safety(request, record)
    response.headers["Cache-Control"] = "no-store"
    return safety.status()


@router.post("/check", dependencies=[Depends(verify_csrf)])
def check(request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    """A full integrity check of the live database."""

    safety = _safety(request, record)
    result = check_file(safety.database)
    return {"ok": result == "ok", "result": result}


@router.post("/backups", status_code=201, dependencies=[Depends(verify_csrf)])
def backup_now(
    request: Request, record: SessionRecord = Depends(_current_session)
) -> Dict[str, Any]:
    safety = _safety(request, record)
    connection = request.app.state.entropy_context.database_manager.connection
    try:
        with connection._lock:  # a consistent copy: no writes from this process meanwhile
            return {"backup": safety.backup(connection.connection, reason="manual")}
    except (DatabaseSafetyError, OSError) as exc:
        raise HTTPException(status_code=422, detail=f"The backup failed: {exc}") from None


@router.get("/backups/{name}")
def download_backup(
    name: str, request: Request, record: SessionRecord = Depends(_current_session)
) -> FileResponse:
    safety = _safety(request, record)
    try:
        path = safety.backup_path(name)
    except DatabaseSafetyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=name)


@router.put("/settings", dependencies=[Depends(verify_csrf)])
def save_settings(
    payload: SafetySettings, request: Request, record: SessionRecord = Depends(_current_session)
) -> Dict[str, Any]:
    safety = _safety(request, record)
    try:
        safety.save_settings({k: v for k, v in payload.model_dump().items() if v is not None})
    except DatabaseSafetyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return safety.status()
