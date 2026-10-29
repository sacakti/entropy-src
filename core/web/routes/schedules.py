"""
Schedules: cron jobs that run a workflow or a plugin, their run history,
and retriggering of failed runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import current_project
from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import _require_permission
from lib.models.session import Session
from lib.models.users import User
from lib.runs.background import fire
from lib.runs.cron import CronError
from lib.runs.schedules import RETRYABLE_STATES, ScheduleError, ScheduleStore, next_run

router = APIRouter(prefix="/api/schedules", tags=["schedules"])

SessionRecord = Tuple[Session, str, User]


class ScheduleRequest(BaseModel):
    name: str
    description: str = ""
    kind: str
    target: str
    cron: str
    timezone: str = "UTC"
    node: str = "local"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SchedulePatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[str] = None
    target: Optional[str] = None
    cron: Optional[str] = None
    timezone: Optional[str] = None
    node: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class IdsRequest(BaseModel):
    ids: List[int] = Field(default_factory=list, max_length=500)


def _store(request: Request) -> ScheduleStore:
    context = request.app.state.entropy_context
    if context is None or context.database_manager is None:
        raise HTTPException(status_code=503, detail="Schedule service unavailable.")
    return ScheduleStore(context.database_manager.connection)


def _schedule(request: Request, user: User, schedule_id: int, permission: str) -> Dict:
    """The schedule, if the user has `permission` in its project."""

    store = _store(request)
    schedule = store.get(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    _require_permission(request, user, permission, store.project_of(schedule))
    return schedule


def _http(exc: ScheduleError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


def _check_target(
    request: Request, user: User, data: Dict[str, Any], project_id: int
) -> None:
    """The author must be able to run what they schedule, in the schedule's project."""

    context = request.app.state.entropy_context
    if data.get("kind") == "workflow":
        _require_permission(request, user, "workflows.execute", project_id)
        # Names are unique per project: the workflow must be this project's.
        try:
            context.workflow_manager.get(data.get("target"), project_id=project_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422,
                detail=f"Workflow '{data.get('target')}' is not registered in this project.",
            ) from exc
    elif data.get("kind") == "plugin":
        _require_permission(request, user, "plugins.execute", project_id)
        if not context.plugin_manager.exists(str(data.get("target"))):
            raise HTTPException(
                status_code=422, detail=f"Plugin '{data.get('target')}' is not installed."
            )


@router.get("")
def list_schedules(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    _require_permission(request, user, "schedules.list", project["id"])

    store = _store(request)
    response.headers["Cache-Control"] = "no-store"
    return {
        "items": store.list(project["id"]),
        "failed": store.runs(failed_only=True, limit=200, project_id=project["id"]),
    }


@router.get("/preview")
def preview(
    request: Request,
    cron: str = Query(..., max_length=200),
    tz: str = Query("UTC", alias="timezone", max_length=64),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Validate a cron expression and list its next firings."""

    _, _, user = record
    _require_permission(request, user, "schedules.list")

    moment = datetime.now(timezone.utc)
    upcoming = []
    try:
        for _ in range(5):
            nxt = next_run(cron, tz, moment)
            if nxt is None:
                break
            upcoming.append(nxt.isoformat())
            moment = nxt
    except (CronError, ScheduleError) as exc:
        return {"valid": False, "error": str(exc), "next": []}

    return {"valid": True, "error": None, "next": upcoming}


@router.get("/{schedule_id}")
def get_schedule(
    schedule_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    schedule = _schedule(request, user, schedule_id, "schedules.list")
    store = _store(request)

    response.headers["Cache-Control"] = "no-store"
    return {"schedule": schedule, "runs": store.runs(schedule_id=schedule_id)}


@router.post("", status_code=201, dependencies=[Depends(verify_csrf)])
def create_schedule(
    payload: ScheduleRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    _require_permission(request, user, "schedules.manage", project["id"])

    data = payload.model_dump()
    _check_target(request, user, data, project["id"])

    try:
        schedule = _store(request).create(
            data, int(user.id or 0), user.username, project_id=project["id"]
        )
    except ScheduleError as exc:
        raise _http(exc) from exc
    return {"schedule": schedule}


@router.patch("/{schedule_id}", dependencies=[Depends(verify_csrf)])
def update_schedule(
    schedule_id: int,
    payload: SchedulePatch,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    current = _schedule(request, user, schedule_id, "schedules.manage")
    store = _store(request)

    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    if "kind" in changes or "target" in changes:
        _check_target(request, user, {**current, **changes}, store.project_of(current))

    try:
        schedule = store.update(schedule_id, changes)
    except ScheduleError as exc:
        raise _http(exc) from exc
    return {"schedule": schedule}


@router.post("/delete", dependencies=[Depends(verify_csrf)])
def delete_schedules(
    payload: IdsRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    for schedule_id in payload.ids:
        _schedule(request, user, schedule_id, "schedules.delete")

    from lib.runs.alerts import RunAlerts

    alerts = RunAlerts(_store(request).connection)
    for schedule_id in payload.ids:
        alerts.forget("schedule", schedule_id)
    return {"deleted": _store(request).delete(payload.ids)}


@router.post("/{schedule_id}/trigger", dependencies=[Depends(verify_csrf)])
def trigger_schedule(
    schedule_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Run a schedule now, as the current user."""

    _, _, user = record
    schedule = _schedule(request, user, schedule_id, "schedules.manage")
    store = _store(request)

    return {
        "run": fire(request.app.state.entropy_context, store, schedule, trigger="manual", user=user)
    }


@router.post("/runs/retry", dependencies=[Depends(verify_csrf)])
def retry_runs(
    payload: IdsRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Retrigger failed schedule runs, as the current user."""

    _, _, user = record

    store = _store(request)
    context = request.app.state.entropy_context
    results = []

    for run_id in payload.ids:
        run = store.get_run(run_id)
        if run is None or run["state"] not in RETRYABLE_STATES:
            continue
        schedule = store.get(run["schedule_id"])
        if schedule is None:
            continue
        _require_permission(request, user, "schedules.manage", store.project_of(schedule))
        store.mark_retried(run_id)
        results.append(fire(context, store, schedule, trigger="retry", user=user, retry_of=run_id))

    return {"runs": results}


@router.post("/runs/dismiss", dependencies=[Depends(verify_csrf)])
def dismiss_runs(
    payload: IdsRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    store = _store(request)
    for run_id in payload.ids:
        run = store.get_run(run_id)
        schedule = store.get(run["schedule_id"]) if run else None
        if schedule is not None:
            _require_permission(request, user, "schedules.manage", store.project_of(schedule))

    return {"dismissed": store.dismiss(payload.ids)}
