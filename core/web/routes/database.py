"""
Administration -> Settings -> Database: which database Entropy runs on and
switching it; on SQLite, the state of entropy.db, its guard and backups,
backing up now, checking it, and where backups go.
"""

from __future__ import annotations

import logging
from threading import Thread
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.web.projects import require
from core.web.routes.auth import _current_session, verify_csrf
from lib.database import engine as database_engine
from lib.database.safety import DatabaseSafetyError, check_file
from lib.models.session import Session
from lib.models.users import User

LOGGER = logging.getLogger("entropy.database")

router = APIRouter(prefix="/api/admin/database", tags=["administration"])

SessionRecord = Tuple[Session, str, User]


class EngineRequest(BaseModel):
    engine: str = Field(max_length=20)


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
    require(request, record[2], "system.settings")
    response.headers["Cache-Control"] = "no-store"
    manager = request.app.state.entropy_context.database_manager
    info = database_engine.public(database_engine.load(manager.database))
    if manager.safety is None:
        return {"engine": info}
    return {**manager.safety.status(), "engine": info}


def _restart_after_switch() -> bool:
    """Restart on the new engine; False when this server was not installed, so cannot."""

    from lib.system import install, web

    if not install.record_path().exists():
        return False
    web.reexec_current_server()
    return True


def _refuse_while_running(context: Any) -> None:
    from lib.runs.store import RunStore

    active = RunStore(context.database_manager.connection).active()
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"{len(active)} run(s) are active. Switch the database when they have finished.",
        )


def _start_in_background(work: Callable[[], None]) -> None:
    Thread(target=work, name="entropy-database-switch", daemon=True).start()


def _read_only(connection: Any, value: bool) -> None:
    """Stop or allow writes through the server's connection; reads go on."""

    with connection._lock:
        connection.connection.execute(f"PRAGMA query_only = {'ON' if value else 'OFF'}")


def _copy_and_record(context: Any, values: Dict[str, Any]) -> None:
    """
    Copy SQLite to PostgreSQL or Oracle, record it as the engine and restart. Runs beside the
    server, which keeps answering (Vision and this page report the progress), but
    cannot change anything the copy would miss. SQLite stays read-only once copied.
    """

    from lib.database.connection import DatabaseConnection
    from lib.database.switch import PROGRESS, copy_database
    from lib.vault.key import VaultKeyProvider

    manager = context.database_manager
    # A connection of its own, so the copy never waits on or blocks the server's.
    reader = DatabaseConnection(manager.database)
    target = None
    try:
        _read_only(manager.connection, True)
        reader.execute("BEGIN")
        target = database_engine.server_connection(values, manager.database)
        copy_database(reader, target, PROGRESS)
        key = VaultKeyProvider(context.executor, context.bootstrap.vault.key).key()
        database_engine.save(manager.database, values, key)
        restarting = _restart_after_switch()
        PROGRESS.update(state="restarting" if restarting else "restart_required", table=None)
    except Exception as error:  # noqa: BLE001 - reported on the page that started it
        LOGGER.warning("Switching the database failed: %s", error)
        _read_only(manager.connection, False)
        PROGRESS.update(state="failed", table=None, error=str(error))
    finally:
        reader.close()
        if target is not None:
            target.close()


def _switch_to_server(context: Any, engine: str) -> None:
    """Check what the switch needs, then copy in the background."""

    from lib.database.switch import PROGRESS
    from lib.system.settings import settings_for

    label = database_engine.LABELS[engine]
    values = settings_for(context).values("database_target")
    if values.get("engine") != engine:
        raise HTTPException(
            status_code=422,
            detail=f"The saved connection is not {label}: save the {label} connection first.",
        )
    if not values.get("host") or not values.get("database"):
        raise HTTPException(status_code=422, detail=f"Save the {label} connection first.")
    if not PROGRESS.begin(engine):
        raise HTTPException(status_code=409, detail="The database is already being switched.")
    _start_in_background(lambda: _copy_and_record(context, values))


@router.get("/switch")
def switch_progress(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """How far a switch has come."""

    from lib.database.switch import PROGRESS

    require(request, record[2], "system.settings")
    response.headers["Cache-Control"] = "no-store"
    return PROGRESS.snapshot()


@router.post("/engine", dependencies=[Depends(verify_csrf)])
def switch_engine(
    payload: EngineRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """
    Switch the database Entropy runs on. Going to PostgreSQL or Oracle copies everything
    from SQLite once, in the background (see /switch for how far it has come);
    going back resumes the SQLite file as it was left.
    """

    require(request, record[2], "system.settings")
    context = request.app.state.entropy_context
    manager = context.database_manager
    current = manager.engine
    if payload.engine == current:
        raise HTTPException(status_code=409, detail=f"Entropy already runs on {current}.")
    _refuse_while_running(context)

    if payload.engine == database_engine.SQLITE:
        database_engine.remove(manager.database)
        return {"engine": payload.engine, "switching": False, "restarting": _restart_after_switch()}
    if payload.engine not in database_engine.SERVER_ENGINES:
        raise HTTPException(status_code=422, detail=f"Entropy cannot run on '{payload.engine}'.")
    if current != database_engine.SQLITE:
        raise HTTPException(status_code=422, detail="Switch back to SQLite first.")
    _switch_to_server(context, payload.engine)
    return {"engine": payload.engine, "switching": True, "restarting": False}


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
