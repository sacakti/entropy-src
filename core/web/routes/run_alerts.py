"""
E-mail alerts when a workflow's or a schedule's runs finish.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import projects, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.session import Session
from lib.models.users import User
from lib.runs.alerts import RunAlerts
from lib.runs.schedules import ScheduleStore

router = APIRouter(tags=["runs"])

SessionRecord = Tuple[Session, str, User]


class AlertSettings(BaseModel):
    emails: List[str] = Field(default_factory=list, max_length=50)
    on_success: bool = False
    on_failure: bool = True
    on_cancel: bool = False


def _alerts(request: Request) -> RunAlerts:
    return RunAlerts(request.app.state.entropy_context.database_manager.connection)


def _mail_ready(request: Request) -> bool:
    from lib.system.settings import settings_for

    return bool(settings_for(request.app.state.entropy_context).get("smtp")["enabled"])


def _workflow_project(request: Request, name: str) -> int:
    try:
        request.app.state.entropy_context.workflow_manager.get(name)
    except Exception:  # noqa: BLE001 - unknown workflow
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found.") from None
    return projects(request).workflow_project(name)


def _schedule_project(request: Request, schedule_id: int) -> int:
    store = ScheduleStore(request.app.state.entropy_context.database_manager.connection)
    schedule = store.get(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    return store.project_of(schedule)


@router.get("/api/workflows/{name}/alerts")
def get_workflow_alerts(
    name: str,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    require(request, user, "workflows.read", _workflow_project(request, name))
    response.headers["Cache-Control"] = "no-store"
    return {**_alerts(request).get("workflow", name), "mail_ready": _mail_ready(request)}


@router.put("/api/workflows/{name}/alerts", dependencies=[Depends(verify_csrf)])
def set_workflow_alerts(
    name: str,
    payload: AlertSettings,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    require(request, user, "workflows.write", _workflow_project(request, name))
    saved = _alerts(request).set("workflow", name, user=user.username, **payload.model_dump())
    return {**saved, "mail_ready": _mail_ready(request)}


@router.get("/api/schedules/{schedule_id}/alerts")
def get_schedule_alerts(
    schedule_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    require(request, user, "schedules.list", _schedule_project(request, schedule_id))
    response.headers["Cache-Control"] = "no-store"
    return {**_alerts(request).get("schedule", schedule_id), "mail_ready": _mail_ready(request)}


@router.put("/api/schedules/{schedule_id}/alerts", dependencies=[Depends(verify_csrf)])
def set_schedule_alerts(
    schedule_id: int,
    payload: AlertSettings,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    require(request, user, "schedules.manage", _schedule_project(request, schedule_id))
    saved = _alerts(request).set(
        "schedule", schedule_id, user=user.username, **payload.model_dump()
    )
    return {**saved, "mail_ready": _mail_ready(request)}
