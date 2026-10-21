"""
Runs API: list workflow jobs, follow them live, stop them, and start
workflow or plugin runs on an execution node.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import current_project, projects
from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import _require_permission
from lib.models.session import Session
from lib.models.users import User
from lib.runs.housekeeping import Housekeeping
from lib.runs.service import RunError, RunService
from lib.runs.store import RUN_TABS, iso_utc

router = APIRouter(tags=["runs"])

SessionRecord = Tuple[Session, str, User]


class RunOptionsRequest(BaseModel):
    """Which steps run and where: by default every enabled step on `node`."""

    node: str = "local"
    # Explicit selection (None: all enabled steps), narrowed by tags.
    steps: Optional[List[str]] = Field(default=None, max_length=500)
    tags: List[str] = Field(default_factory=list, max_length=100)
    # Step name -> node, for steps that run elsewhere than `node`.
    step_nodes: Dict[str, str] = Field(default_factory=dict)


class StartRunRequest(RunOptionsRequest):
    """Where to run and with which inputs."""

    variables: Dict[str, Any] = Field(default_factory=dict)


class StartPluginRunRequest(BaseModel):
    node: str = "local"
    arguments: Dict[str, Any] = Field(default_factory=dict)


class HousekeepingRequest(BaseModel):
    archive_after_days: Optional[int] = None
    purge_archive_after_days: Optional[int] = None
    run_now: bool = False


def _service(request: Request) -> RunService:
    context = request.app.state.entropy_context
    if context is None or context.database_manager is None:
        raise HTTPException(status_code=503, detail="Run service unavailable.")
    return RunService(context)


def _http(exc: RunError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


def _run_project(request: Request, job_id: int) -> int:
    """The project a run belongs to (404 if there is no such run)."""

    run = _service(request).store.get(job_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run #{job_id} does not exist.")
    return run.get("project_id") or projects(request).get("default")["id"]


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _event_payload(event: Any) -> Dict[str, Any]:
    return {
        "id": event.id,
        "type": event.event_type,
        "source": event.source,
        "level": event.level,
        "message": event.message,
        "node_type": event.node_type,
        "node_id": event.node_id,
        "node_name": event.node_name,
        "payload": event.payload,
        "created_at": iso_utc(event.created_at.isoformat()) if event.created_at else None,
    }


def _planned_steps(request: Request, run: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Steps of the workflow as defined, so pending ones can be shown."""

    if run["kind"] == "plugin":
        return [{"name": run["target"], "plugin": run["target"], "enabled": True}]

    # Runs record their own plan: the steps as they were when it started.
    recorded = (run.get("options") or {}).get("steps")
    if recorded:
        return recorded

    manager = request.app.state.entropy_context.workflow_manager
    try:
        workflow = manager.get(run["workflow"])
    except Exception:  # noqa: BLE001 - the workflow may have been removed
        return []

    return [
        {"name": step.name, "plugin": step.plugin, "enabled": step.enabled}
        for step in workflow.steps
    ]


# ----------------------------------------------------------------------
# Runs
# ----------------------------------------------------------------------


@router.get("/api/runs")
def list_runs(
    request: Request,
    response: Response,
    tab: str = Query("all"),
    search: str = Query("", max_length=200),
    node: str = Query("", max_length=64),
    user: str = Query("", max_length=128),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """List runs, newest first, filtered by tab (active/completed/failed/cancelled/all)."""

    _, _, current = record
    project = current_project(request, current)
    _require_permission(request, current, "workflows.read", project["id"])

    if tab != "all" and tab not in RUN_TABS:
        raise HTTPException(status_code=422, detail="Unknown tab.")

    service = _service(request)
    items, total = service.store.list(
        tab=tab,
        search=search,
        node=node,
        user=user,
        limit=limit,
        offset=offset,
        project_id=project["id"],
    )
    _no_store(response)
    return {"items": items, "total": total, "counts": service.store.counts(project["id"])}


@router.get("/api/runs/{job_id}")
def get_run(
    job_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, current = record
    _require_permission(request, current, "workflows.read", _run_project(request, job_id))

    service = _service(request)
    run = service.store.get(job_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run #{job_id} does not exist.")

    _no_store(response)
    return {
        "run": run,
        "plan": _planned_steps(request, run),
        "steps": service.store.steps(job_id),
    }


@router.get("/api/runs/{job_id}/events")
def run_events(
    job_id: int,
    request: Request,
    response: Response,
    after: Optional[int] = Query(None, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Events after a cursor plus the current state, for live following."""

    _, _, current = record
    _require_permission(request, current, "workflows.read", _run_project(request, job_id))

    service = _service(request)
    run = service.store.get(job_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run #{job_id} does not exist.")

    if run["coordinated"]:
        # The run's own messages and those of its segments, in order.
        merged = service.store.events(service.store.job_ids(job_id), after, limit)
        _no_store(response)
        return {
            "run": run,
            "steps": service.store.steps(job_id),
            "events": merged,
            "cursor": merged[-1]["id"] if merged else after,
        }

    events = request.app.state.entropy_context.workflow_job_manager.events(
        job_id, after=after, limit=limit
    )
    _no_store(response)
    return {
        "run": run,
        "steps": service.store.steps(job_id),
        "events": [_event_payload(event) for event in events],
        "cursor": events[-1].id if events else after,
    }


@router.get("/api/runs/{job_id}/log")
def run_log(
    job_id: int,
    request: Request,
    response: Response,
    offset: int = Query(0, ge=0),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Raw worker output (stdout/stderr) from a byte offset."""

    _, _, current = record
    _require_permission(request, current, "workflows.read", _run_project(request, job_id))

    service = _service(request)
    if service.store.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Run #{job_id} does not exist.")

    _no_store(response)
    return service.log(job_id, offset)


@router.post("/api/runs/{job_id}/stop", dependencies=[Depends(verify_csrf)])
def stop_run(
    job_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, current = record
    _require_permission(request, current, "workflows.execute", _run_project(request, job_id))

    try:
        return {"run": _service(request).stop(job_id)}
    except RunError as exc:
        raise _http(exc) from exc


# ----------------------------------------------------------------------
# Start
# ----------------------------------------------------------------------


@router.post("/api/workflows/{name}/run", status_code=201, dependencies=[Depends(verify_csrf)])
def run_workflow(
    name: str,
    payload: StartRunRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Validate and start a registered workflow as the current user."""

    _, _, current = record
    project_id = projects(request).workflow_project(name)
    _require_permission(request, current, "workflows.execute", project_id)

    try:
        run = _service(request).start_workflow(
            current,
            name,
            node=payload.node,
            variables=payload.variables,
            steps=payload.steps,
            tags=payload.tags,
            step_nodes=payload.step_nodes,
            project_id=project_id,
        )
    except RunError as exc:
        raise _http(exc) from exc

    return {"run": run}


@router.post("/api/workflows/{name}/plan", dependencies=[Depends(verify_csrf)])
def plan_workflow_run(
    name: str,
    payload: RunOptionsRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Which steps a run with these options would run, where, in which segments."""

    _, _, current = record
    project_id = projects(request).workflow_project(name)
    _require_permission(request, current, "workflows.execute", project_id)

    try:
        _, plan = _service(request).plan(
            name,
            node=payload.node,
            steps=payload.steps,
            tags=payload.tags,
            step_nodes=payload.step_nodes,
        )
    except RunError as exc:
        if exc.status != 422:
            raise _http(exc) from exc
        _no_store(response)
        return {"valid": False, "error": str(exc)}

    _no_store(response)
    return {"valid": True, "plan": plan.snapshot()}


@router.post(
    "/api/plugins/{qualified_name}/run", status_code=201, dependencies=[Depends(verify_csrf)]
)
def run_plugin(
    qualified_name: str,
    payload: StartPluginRunRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Run an installed plugin once (test run) as the current user."""

    _, _, current = record
    project = current_project(request, current)
    _require_permission(request, current, "plugins.execute", project["id"])

    try:
        run = _service(request).start_plugin(
            current,
            qualified_name,
            node=payload.node,
            arguments=payload.arguments,
            project_id=project["id"],
        )
    except RunError as exc:
        raise _http(exc) from exc

    return {"run": run}


# ----------------------------------------------------------------------
# Housekeeping
# ----------------------------------------------------------------------


def _housekeeping_payload(housekeeping: Housekeeping) -> Dict[str, Any]:
    settings = housekeeping.settings()
    return {
        "archive_after_days": settings["runs.archive_after_days"],
        "purge_archive_after_days": settings["runs.purge_archive_after_days"],
        "archived": housekeeping.archive_counts(),
    }


@router.get("/api/runs-housekeeping")
def get_housekeeping(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, current = record
    _require_permission(request, current, "workflows.read")

    service = _service(request)
    _no_store(response)
    return _housekeeping_payload(Housekeeping(service.store.connection))


@router.put("/api/runs-housekeeping", dependencies=[Depends(verify_csrf)])
def update_housekeeping(
    payload: HousekeepingRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Change the archive policy and optionally apply it now."""

    _, _, current = record
    _require_permission(request, current, "workflows.write")

    service = _service(request)
    housekeeping = Housekeeping(service.store.connection)

    values = {}
    if payload.archive_after_days is not None:
        values["runs.archive_after_days"] = payload.archive_after_days
    if payload.purge_archive_after_days is not None:
        values["runs.purge_archive_after_days"] = payload.purge_archive_after_days

    try:
        housekeeping.update_settings(values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = None
    if payload.run_now:
        result = housekeeping.run(
            plugin_runs=service.plugin_run_directory(),
            worker_logs=service.log_path(0).parent,
        )

    return {**_housekeeping_payload(housekeeping), "result": result}
