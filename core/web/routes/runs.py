"""
Runs API: list workflow jobs, follow them live, stop them, and start
workflow or plugin runs on an execution node.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from core.version import VERSION
from core.web.projects import current_project, projects
from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import _require_permission
from lib.models.session import Session
from lib.models.users import User
from lib.runs.housekeeping import Housekeeping
from lib.runs.plan import PlanError, build_plan
from lib.runs.report import (
    build_report,
    collect_events,
    read_console,
    render_html,
    render_pdf,
    resolve_zone,
)
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
    definition: Optional[str] = None


class StartRunRequest(RunOptionsRequest):
    """Where to run and with which inputs."""

    variables: Dict[str, Any] = Field(default_factory=dict)
    # "interactive": plugins may ask for input on the run screen.
    mode: Literal["automated", "interactive"] = "automated"


class StartPluginRunRequest(BaseModel):
    node: str = "local"
    arguments: Dict[str, Any] = Field(default_factory=dict)
    # Debug messages and full tracebacks in the run log.
    debug: bool = False
    mode: Literal["automated", "interactive"] = "automated"


class HousekeepingRequest(BaseModel):
    archive_after_days: Optional[int] = None
    purge_archive_after_days: Optional[int] = None
    archive_rules: Optional[Dict[str, Any]] = None
    run_now: bool = False


class PurgeArchiveRequest(BaseModel):
    older_than_days: Optional[int] = Field(default=None, ge=1, le=36500)
    purge_all: bool = False


class SelectedRunsRequest(BaseModel):
    job_ids: List[int] = Field(..., min_length=1, max_length=500)


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
        workflow = manager.get(run["workflow"], project_id=run.get("project_id"))
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
    sort: str = Query("started", max_length=20),
    order: Literal["asc", "desc"] = Query("desc"),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """List runs (newest first by default), filtered by tab (active/completed/failed/...)."""

    _, _, current = record
    project = current_project(request, current)
    _require_permission(request, current, "workflows.read", project["id"])

    if tab != "all" and tab != "archived" and tab not in RUN_TABS:
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
        sort=sort if sort in service.store.SORTS else "started",
        order=order,
    )
    if tab == "active":
        _add_waiting_counts(request, items)
    _no_store(response)
    return {"items": items, "total": total, "counts": service.store.counts(project["id"])}


def _add_waiting_counts(request: Request, items: List[Dict[str, Any]]) -> None:
    """Mark active runs that wait on someone: a plugin's question or a paused step."""

    from lib.runs.prompts import PromptStore

    # Only counts are read, so no vault key is needed (this runs on every Vision poll).
    connection = request.app.state.entropy_context.database_manager.connection
    counts = PromptStore(connection).waiting_counts([item["id"] for item in items])
    for item in items:
        item["waiting_for_input"] = counts.get(item["id"], 0)


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


@router.get("/api/runs/{job_id}/artifacts")
def run_artifacts(
    job_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Artifacts the run's steps generated, each naming its step, with a download link."""

    _, _, current = record
    project_id = _run_project(request, job_id)
    _require_permission(request, current, "workflows.read", project_id)
    _require_permission(request, current, "artifacts.read", project_id)

    items = _artifact_items(request, job_id, project_id)
    _no_store(response)
    return {"items": items}


def _artifact_items(request: Request, job_id: int, project_id: int) -> List[Dict[str, Any]]:
    from pathlib import Path

    from lib.artifacts.store import ArtifactStore, ensure_artifacts_schema

    store = _service(request).store
    runs = [store.get(item) for item in store.job_ids(job_id)]
    execution_ids = [str(run["execution_id"]) for run in runs if run and run.get("execution_id")]
    connection = request.app.state.entropy_context.database_manager.connection
    ensure_artifacts_schema(connection)
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "size_bytes": item["size_bytes"],
            "step_name": item.get("step_name"),
            "origin": item.get("origin"),
            "created_at": iso_utc(item["created_at"]) if item.get("created_at") else None,
            "download_url": f"/api/artifacts/{item['id']}/download",
            # Generated files stay where the plugin wrote them; they may be cleaned up.
            "available": bool(item.get("server_path")) and Path(item["server_path"]).is_file(),
        }
        for item in ArtifactStore(connection).for_runs(project_id, execution_ids)
    ]


@router.get("/api/runs/{job_id}/rerun-config")
def get_rerun_config(
    job_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Return saved inputs for the run dialog to prefill (execute access only)."""

    _, _, current = record
    project_id = _run_project(request, job_id)
    service = _service(request)
    run = service.store.get(job_id)
    kind = run["kind"] if run is not None else "workflow"
    permission = "plugins.execute" if kind == "plugin" else "workflows.execute"
    _require_permission(request, current, permission, project_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run #{job_id} does not exist.")
    config = service.store.rerun_config(job_id)
    if config is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "This older run has no saved input configuration."
                f" Start it from the {kind} instead."
            ),
        )
    _no_store(response)
    return {"config": config}


@router.post("/api/runs/{job_id}/rerun", status_code=201, dependencies=[Depends(verify_csrf)])
def rerun_workflow(
    job_id: int,
    payload: StartRunRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Start another execution from this run's saved workflow definition."""

    _, _, current = record
    _require_permission(request, current, "workflows.execute", _run_project(request, job_id))
    service = _service(request)
    original = service.store.get(job_id)
    if original is None:
        raise HTTPException(status_code=404, detail=f"Run #{job_id} does not exist.")
    if original["kind"] != "workflow":
        raise HTTPException(status_code=422, detail="Only workflow runs can be run again.")
    config = service.store.rerun_config(job_id)
    if not config or not isinstance(config.get("definition"), str):
        raise HTTPException(status_code=409, detail="This run has no saved workflow definition.")
    try:
        run = service.start_workflow(
            current,
            original["workflow"],
            node=payload.node,
            variables=payload.variables,
            steps=payload.steps,
            tags=payload.tags,
            step_nodes=payload.step_nodes,
            project_id=_run_project(request, job_id),
            workflow_definition=config["definition"],
            mode=payload.mode,
        )
    except RunError as exc:
        raise _http(exc) from exc
    _no_store(response)
    return {"run": run}


def _report_extras(
    request: Request, user: User, job_id: int, project_id: int
) -> Dict[str, Any]:
    """What only this person sees on the run page: their look, and artifacts if allowed."""

    from lib.database.repositories.user_preferences import UserPreferencesRepository

    context = request.app.state.entropy_context
    preferences = UserPreferencesRepository(context.database_manager.connection).get(user.id)
    allowed = user.id is not None and context.authorization.has_permission(
        user.id, "artifacts.read", project_id
    )
    return {
        "theme": preferences.get("theme"),
        "accent": preferences.get("accent_color"),
        "artifacts": _artifact_items(request, job_id, project_id) if allowed else [],
        "apps": _app_store(request).list(_service(request).store.job_ids(job_id)),
    }


@router.get("/api/runs/{job_id}/report")
def run_report(
    job_id: int,
    request: Request,
    report_format: Literal["html", "pdf"] = Query("html", alias="format"),
    tz: Optional[str] = Query(None, max_length=64),
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """Download what the run page shows; anyone who can see the run can have it."""

    _, _, current = record
    project_id = _run_project(request, job_id)
    _require_permission(request, current, "workflows.read", project_id)
    service = _service(request)
    store = service.store
    run = store.get(job_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run #{job_id} does not exist.")

    events, omitted = collect_events(store, job_id, run)
    console, console_cut = read_console(service, job_id, run)
    zone, zone_name = resolve_zone(tz)
    report = build_report(
        run,
        _planned_steps(request, run),
        store.steps(job_id),
        events,
        now=datetime.now(timezone.utc),
        omitted=omitted,
        console=console,
        console_cut=console_cut,
        zone=zone,
        zone_name=zone_name,
        version=VERSION,
        **_report_extras(request, current, job_id, project_id),
    )
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(run["target"])).strip("-.") or "run"
    return Response(
        render_pdf(report) if report_format == "pdf" else render_html(report),
        media_type="application/pdf" if report_format == "pdf" else "text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="run-{job_id}-{name}.{report_format}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


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

    if run["coordinated"] or run.get("archived"):
        # The run's own messages and those of its segments, in order.
        merged = service.store.events(
            service.store.job_ids(job_id), after, limit, archived=run.get("archived", False)
        )
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
        "prompts": _waiting_prompts(request, run),
    }


def _waiting_prompts(request: Request, run: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Questions the run waits on: plugin inputs (interactive runs) or a paused step."""

    from lib.runs.prompts import prompts_for
    from lib.runs.service import ACTIVE_STATES

    store = prompts_for(request.app.state.entropy_context)
    if run["state"] not in ACTIVE_STATES:
        # The run ended: nothing will read an answer any more.
        store.expire([run["id"]])
        return []
    return store.list([run["id"]], waiting_only=True)


class PromptAnswerRequest(BaseModel):
    value: str = Field(default="", max_length=65536)


@router.post("/api/runs/{job_id}/prompts/{prompt_id}", dependencies=[Depends(verify_csrf)])
def answer_prompt(
    job_id: int,
    prompt_id: int,
    payload: PromptAnswerRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Answer a question of an interactive run: its starter, or who may run workflows."""

    from lib.runs.prompts import PromptError, prompts_for

    _, _, current = record
    project_id = _run_project(request, job_id)
    _require_permission(request, current, "workflows.read", project_id)
    service = _service(request)
    run = service.store.get(job_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run #{job_id} does not exist.")
    if run.get("username") != current.username:
        _require_permission(request, current, "workflows.execute", project_id)

    store = prompts_for(request.app.state.entropy_context)
    prompt = store.get(prompt_id)
    if prompt is None or prompt["job_id"] != job_id:
        raise HTTPException(status_code=404, detail="That question does not belong to this run.")
    try:
        answered = store.answer(prompt_id, payload.value, current.username)
    except PromptError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _no_store(response)
    answered.pop("job_id", None)
    return {"prompt": answered}


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
    if service.store.is_archived(job_id):
        return {"offset": offset, "size": 0, "text": ""}
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
        stopped = _service(request).stop(job_id)
    except RunError as exc:
        raise _http(exc) from exc
    # A stopped run leaves no app page waiting for input.
    from lib.runs.apps import AppStore

    connection = request.app.state.entropy_context.database_manager.connection
    AppStore(connection).finish_jobs(_service(request).store.job_ids(job_id))
    return {"run": stopped}


# ----------------------------------------------------------------------
# App plugins
# ----------------------------------------------------------------------


class AppInputsRequest(BaseModel):
    values: Dict[str, Any] = Field(default_factory=dict)


class AppEventRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    selection: List[Any] = Field(default_factory=list, max_length=5000)


def _app_store(request: Request) -> Any:
    from lib.runs.apps import AppStore

    return AppStore(request.app.state.entropy_context.database_manager.connection)


def _run_app(
    request: Request, current: User, job_id: int, app_id: int, *, act: bool
) -> Dict[str, Any]:
    """The run's app; acting on it (inputs, buttons, stop) needs the starter or execute."""

    project_id = _run_project(request, job_id)
    _require_permission(request, current, "workflows.read", project_id)
    store = _service(request).store
    app: Optional[Dict[str, Any]] = _app_store(request).get(app_id)
    if app is None or app["job_id"] not in store.job_ids(job_id):
        raise HTTPException(status_code=404, detail="That app does not belong to this run.")
    if act:
        run = store.get(job_id) or {}
        if run.get("username") != current.username:
            _require_permission(request, current, "workflows.execute", project_id)
    return app


@router.get("/api/runs/{job_id}/apps")
def run_apps(
    job_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """The live pages of the run's app plugins: definition, inputs, views and state."""

    _, _, current = record
    _require_permission(request, current, "workflows.read", _run_project(request, job_id))
    items = _app_store(request).list(_service(request).store.job_ids(job_id))
    _no_store(response)
    return {"items": items}


@router.put("/api/runs/{job_id}/apps/{app_id}/inputs", dependencies=[Depends(verify_csrf)])
def set_app_inputs(
    job_id: int,
    app_id: int,
    payload: AppInputsRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    from lib.runs.apps import AppError

    _, _, current = record
    _run_app(request, current, job_id, app_id, act=True)
    try:
        return {"inputs": _app_store(request).set_inputs(app_id, payload.values)}
    except AppError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/api/runs/{job_id}/apps/{app_id}/events",
    status_code=201,
    dependencies=[Depends(verify_csrf)],
)
def press_app_button(
    job_id: int,
    app_id: int,
    payload: AppEventRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    from lib.runs.apps import AppError

    _, _, current = record
    app = _run_app(request, current, job_id, app_id, act=True)
    try:
        _app_store(request).push_event(
            app_id, payload.name, {"selection": payload.selection, "values": app["inputs"]},
            current.username,
        )
    except AppError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/api/runs/{job_id}/apps/{app_id}/stop", dependencies=[Depends(verify_csrf)])
def stop_app(
    job_id: int,
    app_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Ask the app to end its loop; the step then completes normally."""

    from lib.runs.apps import AppError

    _, _, current = record
    _run_app(request, current, job_id, app_id, act=True)
    try:
        _app_store(request).request_stop(app_id)
    except AppError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


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
    # Workflow names are unique per project: this is the current project's.
    project_id = current_project(request, current)["id"]
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
            mode=payload.mode,
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
    # Workflow names are unique per project: this is the current project's.
    project_id = current_project(request, current)["id"]
    _require_permission(request, current, "workflows.execute", project_id)

    try:
        if payload.definition is not None:
            manager = request.app.state.entropy_context.workflow_manager
            workflow = manager.deserialize(payload.definition)
            if workflow.name != name:
                raise RunError("Workflow definition does not match the requested workflow.", 422)
            manager._validator.validate(workflow)
            plan = build_plan(
                workflow,
                default_node=payload.node,
                steps=payload.steps,
                tags=payload.tags,
                step_nodes=payload.step_nodes,
            )
        else:
            _, plan = _service(request).plan(
                name,
                project_id=project_id,
                node=payload.node,
                steps=payload.steps,
                tags=payload.tags,
                step_nodes=payload.step_nodes,
            )
    except PlanError as exc:
        _no_store(response)
        return {"valid": False, "error": str(exc)}
    except Exception as exc:
        if isinstance(exc, RunError):
            _no_store(response)
            return {"valid": False, "error": str(exc)}
        _no_store(response)
        return {"valid": False, "error": str(exc) or "Unable to validate the workflow plan."}

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
            debug=payload.debug,
            mode=payload.mode,
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
        "archive_rules": settings["runs.archive_rules"],
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
    if payload.archive_rules is not None:
        values["runs.archive_rules"] = payload.archive_rules

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


@router.post("/api/runs-housekeeping/purge", dependencies=[Depends(verify_csrf)])
def purge_archived_runs(
    payload: PurgeArchiveRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Purge archived runs by age or remove the entire archive."""

    _, _, current = record
    _require_permission(request, current, "workflows.write")
    service = _service(request)
    housekeeping = Housekeeping(service.store.connection)
    project = current_project(request, current)
    days = payload.older_than_days
    if days is None:
        days = housekeeping.settings()["runs.purge_archive_after_days"]
    try:
        purged = housekeeping.purge_archive(
            days, purge_all=payload.purge_all, project_id=project["id"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _no_store(response)
    return {"purged_jobs": purged, "archived": housekeeping.archive_counts()}


@router.post("/api/runs-housekeeping/export", dependencies=[Depends(verify_csrf)])
def export_archived_runs(
    payload: PurgeArchiveRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """Download selected archived runs, metadata and events as a tar.gz."""

    _, _, current = record
    _require_permission(request, current, "workflows.read")
    service = _service(request)
    housekeeping = Housekeeping(service.store.connection)
    project = current_project(request, current)
    days = payload.older_than_days
    if days is None and not payload.purge_all:
        days = housekeeping.settings()["runs.purge_archive_after_days"]
        if days <= 0:
            raise HTTPException(
                status_code=422,
                detail="Choose an age cutoff or export all archived runs.",
            )
    archive = housekeeping.export_archive(
        project_id=project["id"],
        older_than_days=days,
        export_all=payload.purge_all,
    )
    return Response(
        content=archive,
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="entropy-runs-archive.tar.gz"'},
    )


@router.post("/api/runs-housekeeping/archive-selected", dependencies=[Depends(verify_csrf)])
def archive_selected_runs(
    payload: SelectedRunsRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Archive selected finished runs in the current project."""

    _, _, current = record
    _require_permission(request, current, "workflows.write")
    service = _service(request)
    project = current_project(request, current)
    try:
        result = Housekeeping(service.store.connection).archive_selected(
            payload.job_ids, project["id"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"result": result}


@router.post("/api/runs-housekeeping/purge-selected", dependencies=[Depends(verify_csrf)])
def purge_selected_runs(
    payload: SelectedRunsRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Purge selected archived runs in the current project."""

    _, _, current = record
    _require_permission(request, current, "workflows.write")
    service = _service(request)
    project = current_project(request, current)
    housekeeping = Housekeeping(service.store.connection)
    try:
        purged = housekeeping.purge_selected(payload.job_ids, project["id"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _no_store(response)
    return {"purged_jobs": purged, "archived": housekeeping.archive_counts()}


@router.post("/api/runs-housekeeping/export-selected", dependencies=[Depends(verify_csrf)])
def export_selected_runs(
    payload: SelectedRunsRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """Export selected archived runs and their events as a tar.gz."""

    _, _, current = record
    _require_permission(request, current, "workflows.read")
    service = _service(request)
    project = current_project(request, current)
    try:
        archive = Housekeeping(service.store.connection).export_archive(
            project_id=project["id"], job_ids=payload.job_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=archive,
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="entropy-selected-runs.tar.gz"'},
    )
