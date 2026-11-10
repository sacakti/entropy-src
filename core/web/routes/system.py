"""
System administration: installation details, the web server, and
upgrades from release packages (upload, inspect, apply, rollback).

An upgrade runs in a background thread and is followed through
/api/system/upgrade; its state is kept on disk because a successful
upgrade restarts this server on the new code.
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import _require_permission
from lib.models.session import Session
from lib.models.users import User
from lib.system import install, upgrade_notice, web
from lib.system.upgrade import MAX_PACKAGE_BYTES, ReleaseUpgrader, UpgradeError

router = APIRouter(prefix="/api/system", tags=["system"])

SessionRecord = Tuple[Session, str, User]

PERMISSION = "upgrade.entropy"
CHUNK = 1 << 20

_JOB_LOCK = threading.Lock()
# Jobs only run inside this process; a "running" state left by a process
# that died is stale.
_ACTIVE = threading.Event()
# Set to call off an upgrade still waiting for people to save their work.
_CANCEL = threading.Event()
# Minutes people get to save their work before an upgrade begins.
DEFAULT_NOTICE_MINUTES = 5
MAX_NOTICE_MINUTES = 60


def _uploads() -> Path:
    return install.entropy_home() / "run" / "upgrades"


def _job_file() -> Path:
    return install.entropy_home() / "run" / "upgrade-status.json"


def _read_job() -> Dict[str, Any]:
    try:
        return json.loads(_job_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "idle", "log": []}


def _write_job(job: Dict[str, Any]) -> None:
    path = _job_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(job), encoding="utf-8")
    temporary.replace(path)


def _package(upload_id: str) -> Path:
    try:
        uuid.UUID(hex=upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown package.") from exc
    path = _uploads() / f"{upload_id}.tar.gz"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The package is gone; upload it again.")
    return path


def _admin(request: Request, record: SessionRecord) -> User:
    _, _, user = record
    _require_permission(request, user, PERMISSION)
    return user


# ----------------------------------------------------------------------
# Information
# ----------------------------------------------------------------------


@router.get("")
def system_info(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Installation, web server and upgrade history."""

    _admin(request, record)
    from core.version import VERSION

    details = install.load()
    response.headers["Cache-Control"] = "no-store"
    return {
        "version": VERSION,
        "python": sys.version.split()[0],
        "python_executable": details["python"],
        "deps": details["deps"],
        "index_url": details.get("index_url"),
        "platform": details.get("platform"),
        "installed_at": details.get("installed_at"),
        "application": details["application"],
        "home": str(install.entropy_home()),
        "installed": install.record_path().exists(),
        "container": install.in_container(),
        "web": {**web.status(), "service": details["web"]["service"]},
        "upgrades": list(reversed(details.get("upgrades", []))),
        "can_rollback": ReleaseUpgrader().can_rollback(),
        "job": _read_job(),
    }


# ----------------------------------------------------------------------
# Upgrade
# ----------------------------------------------------------------------


@router.post("/upgrade/package", dependencies=[Depends(verify_csrf)])
async def upload_package(
    request: Request,
    file: UploadFile = File(...),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Store a release package and describe it; nothing is changed yet."""

    _admin(request, record)

    name = (file.filename or "").rsplit("/", 1)[-1]
    if not name.endswith((".tar.gz", ".tgz")):
        raise HTTPException(
            status_code=400,
            detail="Upload an Entropy release package (entropy-<version>-<platform>.tar.gz).",
        )

    directory = _uploads()
    # Only the latest upload is kept.
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    upload_id = uuid.uuid4().hex
    target = directory / f"{upload_id}.tar.gz"

    size = 0
    with target.open("wb") as handle:
        while True:
            chunk = await file.read(CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_PACKAGE_BYTES:
                handle.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="The package is larger than 1 GB.")
            handle.write(chunk)

    try:
        info = ReleaseUpgrader().inspect(target)
    except UpgradeError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"id": upload_id, "filename": name, **info}


@router.delete("/upgrade/package/{upload_id}", dependencies=[Depends(verify_csrf)])
def discard_package(
    upload_id: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _admin(request, record)
    _package(upload_id).unlink(missing_ok=True)
    return {"ok": True}


class ApplyRequest(BaseModel):
    id: str
    allow_downgrade: bool = False
    notice_minutes: int = Field(default=DEFAULT_NOTICE_MINUTES, ge=0, le=MAX_NOTICE_MINUTES)


class RollbackRequest(BaseModel):
    notice_minutes: int = Field(default=DEFAULT_NOTICE_MINUTES, ge=0, le=MAX_NOTICE_MINUTES)


def _run(work, connection: Any) -> None:
    """Run an upgrade or rollback, logging to the job file, then restart."""

    job = _read_job()

    def progress(message: str) -> None:
        job["log"].append({"at": datetime.now(timezone.utc).isoformat(), "message": message})
        _write_job(job)

    try:
        entry = work(progress)
    except Exception as exc:  # noqa: BLE001 - every failure is reported to the UI
        job.update(state="failed", error=str(exc), finished_at=_now())
        progress(f"Failed: {exc}")
        _end_notice(job, connection)
        return

    job.update(state="restarting", target=entry["to"], finished_at=_now())
    # Ended here, by this server: the new version starting next may not know the notice.
    _end_notice(job, connection)
    progress("Restarting the web server…")
    web.reexec_current_server()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connection(request: Request) -> Any:
    context = request.app.state.entropy_context
    manager = getattr(context, "database_manager", None)
    return manager.connection if manager is not None else None


def _end_notice(job: Dict[str, Any], connection: Any) -> None:
    """Stop broadcasting the job's notice to everyone, once."""

    if connection is None or job.get("notice_ended"):
        return
    upgrade_notice.end(connection, job.get("notice"))
    job["notice_ended"] = True
    _write_job(job)


def settle_after_restart(context: Any) -> None:
    """
    On start: the upgrade this server restarted for is over (or died with the old
    server), so the broadcast that announced it stops.
    """

    manager = getattr(context, "database_manager", None)
    job = _read_job()
    if manager is None or not job.get("notice") or job.get("notice_ended"):
        return
    if job.get("state") in ("restarting", "running", "waiting"):
        _end_notice(job, manager.connection)


def _wait_for_people(job: Dict[str, Any], minutes: int) -> bool:
    """Let people save their work first; False when the upgrade was cancelled."""

    if minutes <= 0:
        return True
    _CANCEL.wait(minutes * 60)
    # Under the lock: a cancel either lands before the job starts, or is refused.
    with _JOB_LOCK:
        if _CANCEL.is_set():
            return False
        job = _read_job()
        job.update(state="running", started_at=_now())
        job["log"].append({"at": _now(), "message": "Starting now."})
        _write_job(job)
    return True


def _start(
    action: str,
    user: User,
    target: Optional[str],
    work,
    connection: Any = None,
    notice_minutes: int = 0,
) -> Dict[str, Any]:
    """
    Tell everyone through Vision, wait `notice_minutes` for them to save their work
    (the job is "waiting" and can be cancelled), then run the job.
    """

    with _JOB_LOCK:
        if _ACTIVE.is_set():
            raise HTTPException(status_code=409, detail="An upgrade is already running.")
        now = datetime.now(timezone.utc)
        starts_at = now + timedelta(minutes=notice_minutes)
        what = "upgrade" if action == "upgrade" else "rollback"
        job: Dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "action": action,
            "state": "waiting" if notice_minutes > 0 else "running",
            "target": target,
            "by": user.username,
            "started_at": now.isoformat(),
            "starts_at": starts_at.isoformat(),
            "notice_minutes": notice_minutes,
            "error": None,
            "log": (
                [
                    {
                        "at": now.isoformat(),
                        "message": f"Everyone was told; the {what} starts in"
                        f" {notice_minutes} minute{'' if notice_minutes == 1 else 's'}.",
                    }
                ]
                if notice_minutes > 0
                else []
            ),
            # The broadcast telling everyone, ended once the job is over.
            "notice": (
                upgrade_notice.announce(
                    connection,
                    action,
                    target,
                    user.username,
                    starts_at if notice_minutes > 0 else None,
                    notice_minutes,
                )
                if connection is not None
                else None
            ),
        }
        _write_job(job)
        _CANCEL.clear()
        _ACTIVE.set()

    def run() -> None:
        try:
            if _wait_for_people(job, notice_minutes):
                _run(work, connection)
            else:
                cancelled = _read_job()
                cancelled.update(state="cancelled", finished_at=_now())
                cancelled["log"].append({"at": _now(), "message": f"The {what} was cancelled."})
                _write_job(cancelled)
                _end_notice(cancelled, connection)
        finally:
            _ACTIVE.clear()

    threading.Thread(target=run, name=f"entropy-{action}", daemon=True).start()
    return job


@router.post("/upgrade", status_code=202, dependencies=[Depends(verify_csrf)])
def apply_upgrade(
    payload: ApplyRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Apply an uploaded package; follow it at GET /api/system/upgrade."""

    user = _admin(request, record)
    if install.in_container():
        raise HTTPException(
            status_code=409, detail="This server runs in a container: deploy a newer image instead."
        )
    package = _package(payload.id)

    try:
        info = ReleaseUpgrader().inspect(package)
    except UpgradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if info["problems"]:
        raise HTTPException(status_code=400, detail=" ".join(info["problems"]))
    if not info["newer"] and not payload.allow_downgrade:
        raise HTTPException(
            status_code=409,
            detail=f"{info['version']} is not newer than the installed {info['current']}.",
        )

    def work(progress):
        entry = ReleaseUpgrader(progress).apply(
            package, allow_downgrade=payload.allow_downgrade, user=user.username
        )
        shutil.rmtree(_uploads(), ignore_errors=True)
        return entry

    return _start(
        "upgrade", user, info["version"], work, _connection(request), payload.notice_minutes
    )


@router.post("/rollback", status_code=202, dependencies=[Depends(verify_csrf)])
def rollback(
    request: Request,
    payload: Optional[RollbackRequest] = None,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Return to the version before the last upgrade, database included."""

    user = _admin(request, record)
    upgrader = ReleaseUpgrader()
    if not upgrader.can_rollback():
        raise HTTPException(status_code=409, detail="There is no previous version to return to.")
    target = upgrader.record["upgrades"][-1]["from"]

    return _start(
        "rollback",
        user,
        target,
        lambda progress: ReleaseUpgrader(progress).rollback(user=user.username),
        _connection(request),
        (payload or RollbackRequest()).notice_minutes,
    )


@router.post("/upgrade/cancel", dependencies=[Depends(verify_csrf)])
def cancel_upgrade(
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Call off an upgrade or rollback still waiting for people to save their work."""

    _admin(request, record)
    with _JOB_LOCK:
        job = _read_job()
        if job.get("state") != "waiting" or not _ACTIVE.is_set():
            raise HTTPException(
                status_code=409, detail="Only an upgrade that has not started can be cancelled."
            )
        _CANCEL.set()
    return job


@router.get("/upgrade")
def upgrade_status(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """The current or last upgrade/rollback, with its log."""

    _admin(request, record)
    from core.version import VERSION

    job = _read_job()
    if job.get("state") in ("running", "waiting") and not _ACTIVE.is_set():
        job.update(state="failed", error="The server stopped during the upgrade.")
        _write_job(job)
    if job.get("state") == "restarting" and job.get("target") == VERSION:
        job["state"] = "succeeded"
        job["log"].append({"at": _now(), "message": f"Entropy {VERSION} is running."})
        _write_job(job)
    response.headers["Cache-Control"] = "no-store"
    return {**job, "version": VERSION}
