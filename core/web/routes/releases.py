"""Project release workflow, task and environment promotion API."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import current_project, projects, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.session import Session
from lib.models.users import User
from lib.releases.store import RELEASE_STAGES, ReleaseStore
from lib.runs.service import RunError, RunService
from lib.tasks.store import TaskStore

router = APIRouter(prefix="/api/releases", tags=["releases"])
SessionRecord = Tuple[Session, str, User]


class ReleaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="", max_length=100)
    environment: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=10000)
    workflow_name: str = Field(min_length=1, max_length=200)
    tags: List[str] = Field(default_factory=list, max_length=20)
    artifact_ids: List[int] = Field(default_factory=list, max_length=100)


class ReleaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    version: Optional[str] = Field(default=None, max_length=100)
    environment: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=10000)
    stage: Optional[str] = None
    tags: Optional[List[str]] = Field(default=None, max_length=20)


class ReleaseTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    remarks: str = Field(default="", max_length=5000)
    assignee: Optional[str] = Field(default=None, max_length=200)


class ReleaseTasksImport(BaseModel):
    tasks: List[ReleaseTaskCreate] = Field(min_length=1, max_length=500)


class TaskIds(BaseModel):
    task_ids: List[int] = Field(min_length=1, max_length=500)


class ArtifactIds(BaseModel):
    artifact_ids: List[int] = Field(min_length=1, max_length=100)


class ArchiveSelection(BaseModel):
    release_ids: List[int] = Field(default_factory=list, max_length=500)
    promotion_ids: List[int] = Field(default_factory=list, max_length=500)


class PromotionCreate(BaseModel):
    release_ids: List[int] = Field(min_length=1, max_length=500)
    target_environment: str = Field(min_length=1, max_length=100)
    promotion_number: Optional[str] = Field(default=None, max_length=100)
    workflow_name: str = Field(default="", max_length=200)


class PromotionStart(BaseModel):
    workflow_name: str = Field(min_length=1, max_length=200)
    node: str = Field(default="local", max_length=64)


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class HousekeepingRule(BaseModel):
    entity: Literal["release", "promotion"]
    older_than_days: int = Field(ge=1, le=36500)
    statuses: List[str] = Field(default_factory=list, max_length=10)


class HousekeepingUpdate(BaseModel):
    rules: List[HousekeepingRule] = Field(default_factory=list, max_length=50)


def _store(request: Request) -> ReleaseStore:
    return ReleaseStore(request.app.state.entropy_context.database_manager.connection)


def _clean_tags(tags: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in tags:
        tag = value.strip()
        if not tag:
            continue
        if len(tag) > 50:
            raise HTTPException(status_code=422, detail="Release tags must be 50 characters or fewer.")
        if tag.casefold() not in seen:
            result.append(tag)
            seen.add(tag.casefold())
    if len(result) > 20:
        raise HTTPException(status_code=422, detail="A release can have at most 20 tags.")
    return result


def _remember_environment(request: Request, name: str, username: str) -> None:
    environment = name.strip()
    if environment:
        connection = request.app.state.entropy_context.database_manager.connection
        with connection.transaction():
            connection.execute(
                "INSERT OR IGNORE INTO release_environments(name,created_by) VALUES (?,?)",
                (environment, username),
            )


def _housekeeping_rules(request: Request, project_id: int) -> List[Dict[str, Any]]:
    connection = request.app.state.entropy_context.database_manager.connection
    row = connection.fetchone("SELECT rules FROM release_housekeeping WHERE project_id = ?", (project_id,))
    if not row:
        return []
    try:
        result = json.loads(row["rules"])
        return result if isinstance(result, list) else []
    except (TypeError, ValueError):
        return []


def _apply_housekeeping(request: Request, project_id: int) -> int:
    rules = _housekeeping_rules(request, project_id)
    if not rules:
        return 0
    connection = request.app.state.entropy_context.database_manager.connection
    archived = 0
    with connection.transaction():
        for rule in rules:
            entity = rule.get("entity")
            if entity not in {"release", "promotion"}:
                continue
            table = "releases" if entity == "release" else "release_promotions"
            status_column = "stage" if entity == "release" else "status"
            days = int(rule.get("older_than_days", 0))
            if days < 1:
                continue
            statuses = [str(value) for value in rule.get("statuses", []) if value]
            if not statuses:
                statuses = ["completed"] if entity == "release" else ["completed", "failed", "cancelled"]
            sql = f"UPDATE {table} SET archived_at = datetime('now') WHERE project_id = ? AND archived_at IS NULL AND created_at <= datetime('now', ?)"
            parameters: List[Any] = [project_id, f"-{days} days"]
            if statuses:
                sql += f" AND {status_column} IN ({','.join('?' for _ in statuses)})"
                parameters.extend(statuses)
            cursor = connection.execute(sql, tuple(parameters))
            archived += max(0, cursor.rowcount)
    return archived


def _project(request: Request, user: User, permission: str) -> Dict[str, Any]:
    project = current_project(request, user)
    require(request, user, permission, project["id"])
    return project


def _release(request: Request, user: User, release_id: int, permission: str) -> Dict[str, Any]:
    item = _store(request).get(release_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Release not found.")
    project = current_project(request, user)
    if item["project_id"] != project["id"]:
        raise HTTPException(status_code=404, detail="Release not found in the current project.")
    require(request, user, permission, project["id"])
    return _sync_run(request, item)


def _workflow(request: Request, name: str, project_id: int) -> None:
    context = request.app.state.entropy_context
    try:
        context.workflow_manager.get(name)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' is not registered.") from None
    if projects(request).workflow_project(name) != project_id:
        raise HTTPException(status_code=422, detail="The selected workflow belongs to a different project.")


def _sync_run(request: Request, item: Dict[str, Any]) -> Dict[str, Any]:
    job_id = item.get("workflow_job_id")
    if not job_id:
        item["workflow_state"] = None
        return item
    run = RunService(request.app.state.entropy_context).store.get(int(job_id))
    item["workflow_state"] = run["state"] if run else "missing"
    # When the associated workflow completes, move the release into its task
    # queue if work is attached, or mark that workflow processing is done.
    if run and run["state"] == "completed" and item["stage"] == "workflow_queue":
        stage = "task_queue" if item["tasks"] else "workflow_done"
        item = _store(request).update(item["id"], {"stage": stage})
        item["workflow_state"] = run["state"]
    return item


def _sync_promotions(request: Request, project_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
    store = _store(request)
    promotions = store.promotions(project_id, include_archived)
    connection = request.app.state.entropy_context.database_manager.connection
    for item in promotions:
        job_id = item.get("workflow_job_id")
        run = RunService(request.app.state.entropy_context).store.get(int(job_id)) if job_id else None
        if not run:
            continue
        item["workflow_state"] = run["state"]
        if run["state"] in {"completed", "failed", "cancelled"} and item["status"] == "running":
            with connection.transaction():
                connection.execute("UPDATE release_promotions SET status = ? WHERE id = ?",
                                   (run["state"], item["id"]))
            item["status"] = run["state"]
            if run["state"] == "completed":
                with connection.transaction():
                    for release in item["releases"]:
                        connection.execute("UPDATE releases SET environment = ?, updated_at = datetime('now') WHERE id = ?",
                                           (item["target_environment"], release["id"]))
                        release["environment"] = item["target_environment"]
    return promotions


@router.get("")
def list_releases(request: Request, response: Response, include_archived: bool = Query(False),
                  record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, user, "releases.read")
    _apply_housekeeping(request, project["id"])
    store = _store(request)
    # Promotions first: a finished one moves its releases to the target environment.
    promotions = _sync_promotions(request, project["id"], include_archived)
    items = [_sync_run(request, item) for item in store.list(project["id"], include_archived)]
    workflows = []
    for entry in request.app.state.entropy_context.workflow_manager.list():
        if projects(request).workflow_project(entry.name) == project["id"]:
            workflows.append({"name": entry.name, "version": entry.version, "description": entry.description or ""})
    response.headers["Cache-Control"] = "no-store"
    assert user.id is not None
    return {
        "items": items,
        "promotions": promotions,
        "environments": [row["name"] for row in request.app.state.entropy_context.database_manager.connection.fetchall(
            "SELECT name FROM release_environments ORDER BY name COLLATE NOCASE")],
        "housekeeping_rules": _housekeeping_rules(request, project["id"]),
        "archived_promotions": [item for item in store.promotions(project["id"], True) if item.get("archived_at")],
        "workflows": workflows,
        "permissions": {name: request.app.state.entropy_context.authorization.has_permission(user.id, name, project["id"])
                        for name in ("releases.create", "releases.manage", "releases.promote", "workflows.execute", "tasks.create", "artifacts.read")},
    }


@router.get("/report.xlsx")
def release_workbook(request: Request, ids: str = Query("", max_length=20000),
                     include_archived: bool = Query(False),
                     record: SessionRecord = Depends(_current_session)) -> Response:
    """Releases, their tasks and a pivot summary as a formatted Excel workbook."""

    import tempfile
    from datetime import datetime
    from pathlib import Path

    from lib.releases.report import build_workbook

    _, _, user = record
    project = _project(request, user, "releases.read")
    wanted = {int(part) for part in ids.split(",") if part.strip().isdigit()}
    promotions = _sync_promotions(request, project["id"], True)
    releases = [_sync_run(request, item) for item in _store(request).list(project["id"], include_archived)]
    if wanted:
        releases = [item for item in releases if item["id"] in wanted]
    if not releases:
        raise HTTPException(status_code=404, detail="No releases to report.")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "releases.xlsx"
        build_workbook(path, project.get("name") or project.get("key") or "Project", releases, promotions,
                       user.full_name or user.username)
        content = path.read_bytes()
    name = f"release-{releases[0]['id']}" if len(releases) == 1 else "releases"
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}-traceability-{stamp}.xlsx"',
                 "Cache-Control": "no-store"},
    )


@router.post("/environments", status_code=201, dependencies=[Depends(verify_csrf)])
def create_environment(payload: EnvironmentCreate, request: Request,
                       record: SessionRecord = Depends(_current_session)) -> Dict[str, str]:
    _, _, user = record
    project = current_project(request, user)
    if not any(request.app.state.entropy_context.authorization.has_permission(user.id, permission, project["id"])
               for permission in ("releases.create", "releases.manage", "releases.promote")):
        raise HTTPException(status_code=403, detail="You cannot manage Release Manager environments in this project.")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Environment name cannot be blank.")
    _remember_environment(request, name, user.username)
    return {"name": name, "project": project["key"]}


@router.put("/housekeeping", dependencies=[Depends(verify_csrf)])
def update_housekeeping(payload: HousekeepingUpdate, request: Request,
                        record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, user, "releases.manage")
    rules = [rule.model_dump() for rule in payload.rules]
    for rule in rules:
        allowed = {"workflow_queue", "workflow_done", "task_queue", "completed", "queued", "running", "failed", "cancelled"}
        if set(rule["statuses"]) - allowed:
            raise HTTPException(status_code=422, detail="A housekeeping rule contains an unsupported status.")
        if rule["entity"] == "release" and set(rule["statuses"]) - {"workflow_queue", "workflow_done", "task_queue", "completed"}:
            raise HTTPException(status_code=422, detail="Choose a valid release stage for the archive rule.")
        if rule["entity"] == "promotion" and set(rule["statuses"]) - {"queued", "running", "completed", "failed", "cancelled"}:
            raise HTTPException(status_code=422, detail="Choose a valid promotion status for the archive rule.")
    connection = request.app.state.entropy_context.database_manager.connection
    with connection.transaction():
        connection.execute(
            "INSERT INTO release_housekeeping(project_id,rules,updated_by) VALUES (?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET rules = excluded.rules, updated_by = excluded.updated_by, updated_at = datetime('now')",
            (project["id"], json.dumps(rules), user.username),
        )
    return {"rules": rules}


@router.post("/housekeeping/run", dependencies=[Depends(verify_csrf)])
def run_housekeeping(request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, int]:
    _, _, user = record
    project = _project(request, user, "releases.manage")
    return {"archived": _apply_housekeeping(request, project["id"])}


@router.post("/archive", dependencies=[Depends(verify_csrf)])
def archive_selected(payload: ArchiveSelection, request: Request,
                     record: SessionRecord = Depends(_current_session)) -> Dict[str, int]:
    _, _, user = record
    project = _project(request, user, "releases.manage")
    release_ids = list(dict.fromkeys(payload.release_ids))
    promotion_ids = list(dict.fromkeys(payload.promotion_ids))
    if not release_ids and not promotion_ids:
        raise HTTPException(status_code=422, detail="Select at least one release or promotion record to archive.")
    connection = request.app.state.entropy_context.database_manager.connection
    archived_releases = 0
    archived_promotions = 0
    with connection.transaction():
        if release_ids:
            placeholders = ",".join("?" for _ in release_ids)
            cursor = connection.execute(
                "UPDATE releases SET archived_at = datetime('now') "
                f"WHERE project_id = ? AND archived_at IS NULL AND id IN ({placeholders})",
                (project["id"], *release_ids),
            )
            archived_releases = max(0, cursor.rowcount)
        if promotion_ids:
            placeholders = ",".join("?" for _ in promotion_ids)
            cursor = connection.execute(
                "UPDATE release_promotions SET archived_at = datetime('now') "
                f"WHERE project_id = ? AND archived_at IS NULL AND id IN ({placeholders})",
                (project["id"], *promotion_ids),
            )
            archived_promotions = max(0, cursor.rowcount)
    return {"archived_releases": archived_releases, "archived_promotions": archived_promotions}


@router.post("", status_code=201, dependencies=[Depends(verify_csrf)])
def create_release(payload: ReleaseCreate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, user, "releases.create")
    require(request, user, "workflows.read", project["id"])
    _workflow(request, payload.workflow_name, project["id"])
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Release name cannot be blank.")
    environment = payload.environment.strip()
    _remember_environment(request, environment, user.username)
    artifact_ids = list(dict.fromkeys(payload.artifact_ids))
    if artifact_ids:
        require(request, user, "artifacts.read", project["id"])
        connection = request.app.state.entropy_context.database_manager.connection
        for artifact_id in artifact_ids:
            artifact = connection.fetchone("SELECT id FROM artifacts WHERE id = ? AND project_id = ?", (artifact_id, project["id"]))
            if artifact is None:
                raise HTTPException(status_code=404, detail="One or more selected artifacts were not found in this project.")
    created = _store(request).create(project["id"], name, payload.version.strip(), environment,
                                     payload.description, payload.workflow_name, user.username,
                                     json.dumps(_clean_tags(payload.tags), ensure_ascii=False))
    if artifact_ids:
        _store(request).link_artifacts(created["id"], artifact_ids)
        created = _store(request).get(created["id"]) or created
    return created


@router.patch("/{release_id}", dependencies=[Depends(verify_csrf)])
def update_release(release_id: int, payload: ReleaseUpdate, request: Request,
                   record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    item = _release(request, user, release_id, "releases.manage")
    data = payload.model_dump(exclude_unset=True)
    if "tags" in data and data["tags"] is not None:
        data["tags"] = json.dumps(_clean_tags(data["tags"]), ensure_ascii=False)
    stage = data.get("stage")
    if stage is not None:
        if stage not in RELEASE_STAGES:
            raise HTTPException(status_code=422, detail="Choose a valid release stage.")
        if stage in {"workflow_done", "task_queue", "completed"}:
            state = item.get("workflow_state")
            if item.get("workflow_job_id") and state != "completed":
                raise HTTPException(status_code=409, detail="The release workflow must complete successfully first.")
        if stage == "completed" and any(task["status"] != "done" for task in item["tasks"]):
            raise HTTPException(status_code=409, detail="Complete all linked tasks before completing the release.")
        if item["stage"] == "completed" and stage != "completed":
            raise HTTPException(status_code=409, detail="Completed releases cannot return to an earlier stage.")
    if item["stage"] == "completed" and "environment" in data:
        raise HTTPException(status_code=409, detail="Promote completed releases through the promotion queue.")
    if "environment" in data and data["environment"]:
        _remember_environment(request, data["environment"], user.username)
    return _store(request).update(release_id, data)


@router.post("/{release_id}/artifacts", status_code=201, dependencies=[Depends(verify_csrf)])
def link_release_artifacts(release_id: int, payload: ArtifactIds, request: Request,
                           record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    release = _release(request, user, release_id, "releases.manage")
    if release["stage"] == "completed":
        raise HTTPException(status_code=409, detail="Completed releases cannot change linked artifacts.")
    require(request, user, "artifacts.read", release["project_id"])
    connection = request.app.state.entropy_context.database_manager.connection
    ids = list(dict.fromkeys(payload.artifact_ids))
    for artifact_id in ids:
        artifact = connection.fetchone("SELECT id FROM artifacts WHERE id = ? AND project_id = ?",
                                       (artifact_id, release["project_id"]))
        if artifact is None:
            raise HTTPException(status_code=404, detail="One or more selected artifacts were not found in this project.")
    _store(request).link_artifacts(release_id, ids)
    return {"release": _store(request).get(release_id)}


@router.delete("/{release_id}/artifacts/{artifact_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def unlink_release_artifact(release_id: int, artifact_id: int, request: Request,
                            record: SessionRecord = Depends(_current_session)) -> Response:
    _, _, user = record
    release = _release(request, user, release_id, "releases.manage")
    if release["stage"] == "completed":
        raise HTTPException(status_code=409, detail="Completed releases cannot change linked artifacts.")
    if not any(item["id"] == artifact_id for item in release["artifacts"]):
        raise HTTPException(status_code=404, detail="Artifact is not linked to this release.")
    connection = request.app.state.entropy_context.database_manager.connection
    with connection.transaction():
        connection.execute("DELETE FROM release_artifacts WHERE release_id = ? AND artifact_id = ?",
                           (release_id, artifact_id))
    return Response(status_code=204)


@router.post("/{release_id}/run", status_code=201, dependencies=[Depends(verify_csrf)])
def run_release_workflow(release_id: int, request: Request,
                         record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    item = _release(request, user, release_id, "releases.manage")
    project_id = item["project_id"]
    require(request, user, "workflows.execute", project_id)
    _workflow(request, item["workflow_name"], project_id)
    if item["stage"] != "workflow_queue":
        raise HTTPException(status_code=409, detail="Only releases in the workflow queue can run their workflow.")
    if item.get("workflow_job_id"):
        previous = RunService(request.app.state.entropy_context).store.get(int(item["workflow_job_id"]))
        if previous and previous["state"] not in {"failed", "cancelled"}:
            raise HTTPException(status_code=409, detail="This release workflow has already started or completed.")
    try:
        run = RunService(request.app.state.entropy_context).start_workflow(
            user, item["workflow_name"], project_id=project_id,
            variables={"release": {"id": item["id"], "name": item["name"], "version": item["version"],
                                   "environment": item["environment"], "description": item["description"]},
                       "release_id": item["id"], "release_name": item["name"], "release_version": item["version"]},
        )
    except RunError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    _store(request).set_run(release_id, int(run["id"]))
    return {"release": _store(request).get(release_id), "run": run}


def _add_task(request: Request, user: User, release: Dict[str, Any], payload: ReleaseTaskCreate) -> Dict[str, Any]:
    if release["stage"] == "completed":
        raise HTTPException(status_code=409, detail="Completed releases cannot accept new tasks.")
    project_id = release["project_id"]
    require(request, user, "tasks.create", project_id)
    if payload.assignee and payload.assignee.lower() != user.username.lower():
        members = projects(request).members(project_id)
        if not any(m.get("kind") == "user" and m.get("name", "").lower() == payload.assignee.lower() for m in members):
            raise HTTPException(status_code=422, detail=f"'{payload.assignee}' is not a member of this project.")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Task title cannot be blank.")
    connection = request.app.state.entropy_context.database_manager.connection
    task = TaskStore(connection).create(project_id, title, payload.description, payload.remarks,
                                        payload.assignee, None, user.username)
    _store(request).link_task(release["id"], int(task["id"]))
    if release["stage"] == "workflow_done":
        _store(request).update(release["id"], {"stage": "task_queue"})
    return task


@router.post("/{release_id}/tasks", status_code=201, dependencies=[Depends(verify_csrf)])
def create_release_task(release_id: int, payload: ReleaseTaskCreate, request: Request,
                        record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    release = _release(request, user, release_id, "releases.manage")
    if release["stage"] == "completed":
        raise HTTPException(status_code=409, detail="Completed releases cannot change linked tasks.")
    return _add_task(request, user, release, payload)


@router.post("/{release_id}/tasks/import", status_code=201, dependencies=[Depends(verify_csrf)])
def import_release_tasks(release_id: int, payload: ReleaseTasksImport, request: Request,
                         record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    release = _release(request, user, release_id, "releases.manage")
    if release["stage"] == "completed":
        raise HTTPException(status_code=409, detail="Completed releases cannot accept new tasks.")
    for task in payload.tasks:
        if not task.title.strip():
            raise HTTPException(status_code=422, detail="Imported task titles cannot be blank.")
        if task.assignee:
            members = projects(request).members(release["project_id"])
            if not any(m.get("kind") == "user" and m.get("name", "").lower() == task.assignee.lower()
                       for m in members):
                raise HTTPException(status_code=422, detail=f"'{task.assignee}' is not a member of this project.")
    added = [_add_task(request, user, release, task) for task in payload.tasks]
    return {"items": added}


@router.post("/{release_id}/tasks/link", status_code=201, dependencies=[Depends(verify_csrf)])
def link_release_tasks(release_id: int, payload: TaskIds, request: Request,
                       record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    release = _release(request, user, release_id, "releases.manage")
    if release["stage"] == "completed":
        raise HTTPException(status_code=409, detail="Completed releases cannot change linked tasks.")
    require(request, user, "tasks.read", release["project_id"])
    connection = request.app.state.entropy_context.database_manager.connection
    ids = list(dict.fromkeys(payload.task_ids))
    tasks = []
    for task_id in ids:
        task = connection.fetchone("SELECT id,project_id FROM tasks WHERE id = ?", (task_id,))
        if task is None or task["project_id"] != release["project_id"]:
            raise HTTPException(status_code=404, detail=f"Task #{task_id} not found in this project.")
        tasks.append(task_id)
    for task_id in tasks:
        _store(request).link_task(release_id, task_id)
    if tasks and release["stage"] == "workflow_done":
        _store(request).update(release_id, {"stage": "task_queue"})
    return {"release": _store(request).get(release_id)}


@router.delete("/{release_id}/tasks/{task_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def unlink_release_task(release_id: int, task_id: int, request: Request,
                        record: SessionRecord = Depends(_current_session)) -> Response:
    _, _, user = record
    release = _release(request, user, release_id, "releases.manage")
    if release["stage"] == "completed":
        raise HTTPException(status_code=409, detail="Completed releases cannot change linked tasks.")
    linked = {task["id"] for task in release["tasks"]}
    if task_id not in linked:
        raise HTTPException(status_code=404, detail="Task is not linked to this release.")
    _store(request).unlink_task(release_id, task_id)
    return Response(status_code=204)


@router.post("/promotions", status_code=201, dependencies=[Depends(verify_csrf)])
def promote_releases(payload: PromotionCreate, request: Request, record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, user, "releases.promote")
    ids = list(dict.fromkeys(payload.release_ids))
    releases = []
    for release_id in ids:
        item = _release(request, user, release_id, "releases.promote")
        if item["stage"] != "completed":
            raise HTTPException(status_code=409, detail=f"Release '{item['name']}' is not completed.")
        releases.append(item)
    target = payload.target_environment.strip()
    if not target:
        raise HTTPException(status_code=422, detail="Give a target environment.")
    if any(item["environment"].strip().casefold() == target.casefold() for item in releases):
        raise HTTPException(status_code=422, detail="Choose an environment different from each selected release's current environment.")
    _remember_environment(request, target, user.username)
    number = payload.promotion_number.strip() if payload.promotion_number else ""
    if number and any((item.get("promotion_number") or "").casefold() == number.casefold()
                      for item in _store(request).promotions(project["id"], include_archived=True)):
        raise HTTPException(status_code=409, detail=f"Promotion number '{number}' is already in use.")
    store = _store(request)
    try:
        promotion_id = store.create_promotion(project["id"], ids, target,
                                              payload.workflow_name.strip(), user.username, number or None)
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="That promotion number is already in use.") from None
        raise
    promotion = next(item for item in store.promotions(project["id"], include_archived=True) if item["id"] == promotion_id)
    return {"promotion": promotion}


@router.post("/promotions/{promotion_id}/run", status_code=201, dependencies=[Depends(verify_csrf)])
def run_promotion(promotion_id: int, payload: PromotionStart, request: Request,
                  record: SessionRecord = Depends(_current_session)) -> Dict[str, Any]:
    _, _, user = record
    project = _project(request, user, "releases.promote")
    require(request, user, "workflows.execute", project["id"])
    _workflow(request, payload.workflow_name, project["id"])
    store = _store(request)
    promotion = next((item for item in store.promotions(project["id"], include_archived=True)
                      if item["id"] == promotion_id), None)
    if promotion is None:
        raise HTTPException(status_code=404, detail="Promotion record not found.")
    if promotion.get("archived_at"):
        raise HTTPException(status_code=409, detail="Archived promotion records cannot be run.")
    if promotion["status"] not in {"queued", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="This promotion record is already running or completed.")
    releases = []
    for release in promotion["releases"]:
        item = _release(request, user, release["id"], "releases.promote")
        if item["stage"] != "completed":
            raise HTTPException(status_code=409, detail=f"Release '{item['name']}' is no longer completed.")
        releases.append(item)
    ids = [item["id"] for item in releases]
    active = {release["id"] for item in _sync_promotions(request, project["id"])
              if item["id"] != promotion_id and item["status"] == "running" for release in item["releases"]}
    if active.intersection(ids):
        raise HTTPException(status_code=409, detail="One or more selected releases already have a promotion in progress.")
    variables = {
        "target_environment": promotion["target_environment"],
        "promotion_number": promotion["promotion_number"],
        "release_ids": ids,
        "releases": [{"id": item["id"], "name": item["name"], "version": item["version"],
                      "environment": item["environment"], "description": item["description"],
                      "tasks": item["tasks"],
                      "task_ids": [task["id"] for task in item["tasks"]]} for item in releases],
    }
    try:
        run = RunService(request.app.state.entropy_context).start_workflow(
            user, payload.workflow_name, node=payload.node, project_id=project["id"],
            variables=variables, trigger="manual",
        )
    except RunError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    store.set_promotion_workflow(promotion_id, payload.workflow_name)
    store.set_promotion_run(promotion_id, int(run["id"]))
    return {"promotion_id": promotion_id, "run": run}
