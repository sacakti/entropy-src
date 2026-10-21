
"""
Authenticated workflow management API.
"""

from __future__ import annotations

import dataclasses
import io
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from core.web.routes.auth import _current_session, verify_csrf
from core.web.versioning import bump_version
from lib.history import DefinitionHistory
from lib.workflow.drafts import WorkflowDrafts
from lib.models.session import Session
from lib.models.users import User
from lib.workflow.exceptions import (
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
    WorkflowNotMatchError,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

SessionRecord = Tuple[Session, str, User]
SUPPORTED_FORMATS = {"json": ".json", "yaml": ".yaml", "yml": ".yml"}
MAX_DEFINITION_LENGTH = 1_000_000


class WorkflowDefinitionRequest(BaseModel):
    """A workflow definition supplied by the browser."""

    definition: str
    format: str = "json"


class WorkflowNamesRequest(BaseModel):
    """Several workflows, for bulk export."""

    names: List[str] = Field(min_length=1, max_length=500)
    format: str = "json"


def _bump_if_unchanged_version(manager, name: str, path: Path, format_name: str) -> None:
    """
    Editing a workflow raises its patch version unless the author changed
    the version themselves.
    """

    try:
        existing = manager.get(name)
        incoming = manager.load(path)
    except Exception:  # noqa: BLE001 - replace() reports these errors
        return

    if incoming.version != existing.version:
        return

    def body(workflow):
        return manager.serialize(dataclasses.replace(workflow, version=""), "json")

    if body(incoming) == body(existing):
        return

    bumped = dataclasses.replace(incoming, version=bump_version(incoming.version))
    path.write_text(manager.serialize(bumped, format_name), encoding="utf-8")


def _manager(request: Request):
    context = request.app.state.entropy_context
    if context.workflow_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Workflow service unavailable.",
        )
    return context.workflow_manager


def _require_permission(
    request: Request,
    user: User,
    permission: str,
) -> None:
    """Enforce Entropy's effective permissions for the browser user."""

    context = request.app.state.entropy_context
    authorization = context.authorization

    if authorization is None:
        raise HTTPException(
            status_code=503,
            detail="Authorization service unavailable.",
        )

    if user.id is None or not authorization.has_permission(user.id, permission):
        raise HTTPException(
            status_code=403,
            detail="Permission denied.",
        )


def _require_any_permission(
    request: Request,
    user: User,
    *permissions: str,
) -> None:
    """Allow the request when the user holds any one of the permissions."""

    authorization = request.app.state.entropy_context.authorization

    if authorization is None:
        raise HTTPException(status_code=503, detail="Authorization service unavailable.")

    if user.id is None or not any(
        authorization.has_permission(user.id, permission) for permission in permissions
    ):
        raise HTTPException(status_code=403, detail="Permission denied.")


def _check_plugin_access(request: Request, user: User, workflow) -> None:
    """
    Authoring a workflow means choosing plugins, so it needs plugins.read;
    every step's plugin must also be enabled. Running a workflow needs only
    workflows.execute: the saved workflow is what grants its plugins.
    """

    authorization = request.app.state.entropy_context.authorization
    if user.id is None or not authorization.has_permission(user.id, "plugins.read"):
        raise HTTPException(
            status_code=403,
            detail=(
                "Workflows are built from plugins: creating, editing or importing "
                "a workflow needs the plugins.read permission."
            ),
        )

    plugins = request.app.state.entropy_context.plugin_manager
    for step in workflow.steps:
        try:
            plugin = plugins.get(step.plugin)
        except Exception:  # noqa: BLE001 - the validator reports unknown plugins
            continue
        if not getattr(plugin, "enabled", True):
            raise HTTPException(
                status_code=422,
                detail=f"Step '{step.name}' uses plugin '{step.plugin}', which is disabled.",
            )


def _clear_drafts(request: Request, name: str) -> None:
    """A workflow saved (or deleted) for real has no draft left."""

    context = request.app.state.entropy_context
    if context.database_manager is not None:
        WorkflowDrafts(context.database_manager.connection).delete_for_workflow(name)


def _validate_format(format_name: str) -> str:
    normalized = format_name.strip().lower()

    if normalized not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=422,
            detail="Format must be json, yaml, or yml.",
        )

    return normalized


def _definition_file(definition: str, format_name: str):
    """Yield a temporary definition file and remove it afterwards."""

    if not definition.strip():
        raise HTTPException(
            status_code=422,
            detail="Workflow definition cannot be empty.",
        )

    if len(definition) > MAX_DEFINITION_LENGTH:
        raise HTTPException(
            status_code=413,
            detail="Workflow definition is too large.",
        )

    suffix = SUPPORTED_FORMATS[format_name]

    with tempfile.TemporaryDirectory(prefix="entropy-web-workflow-") as directory:
        path = Path(directory) / ("definition" + suffix)
        path.write_text(definition, encoding="utf-8")
        yield path


def _workflow_payload(workflow, manager, format_name: str) -> Dict[str, object]:
    return {
        "name": workflow.name,
        "version": workflow.version,
        "description": workflow.description,
        "step_count": workflow.step_count,
        "format": format_name,
        "definition": manager.serialize(workflow, format_name),
    }


def _history(request: Request) -> DefinitionHistory:
    connection = request.app.state.entropy_context.database_manager.connection
    return DefinitionHistory(connection, "workflow")


def _current(manager, name: str):
    try:
        return manager.get(name)
    except WorkflowNotFoundError as exc:
        raise _translate_workflow_error(exc) from exc


def _translate_workflow_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkflowNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))

    if isinstance(exc, WorkflowAlreadyExistsError):
        return HTTPException(status_code=409, detail=str(exc))

    if isinstance(exc, WorkflowNotMatchError):
        return HTTPException(status_code=422, detail=str(exc))

    return HTTPException(status_code=422, detail=str(exc))


@router.get("")
def list_workflows(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, object]:
    """List registered workflows visible to the authenticated user."""

    _, _, user = record
    _require_permission(request, user, "workflows.read")

    manager = _manager(request)
    entries = manager.list()

    response.headers["Cache-Control"] = "no-store"

    return {
        "items": [
            {
                "name": entry.name,
                "version": entry.version,
                "description": entry.description,
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
            }
            for entry in entries
        ]
    }


@router.post("/export")
def export_workflows(
    payload: WorkflowNamesRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Response:
    """Download workflow definitions as one zip, a file each."""

    _, _, user = record
    _require_permission(request, user, "workflows.read")

    normalized_format = _validate_format(payload.format)
    manager = _manager(request)
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in dict.fromkeys(payload.names):
            try:
                workflow = manager.get(name)
            except WorkflowNotFoundError as exc:
                raise _translate_workflow_error(exc) from exc
            archive.writestr(
                f"{workflow.name}{SUPPORTED_FORMATS[normalized_format]}",
                manager.serialize(workflow, normalized_format),
            )

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="entropy-workflows.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{name}")
def get_workflow(
    name: str,
    request: Request,
    response: Response,
    format_name: str = Query("json", alias="format"),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, object]:
    """Return a validated registered workflow definition."""

    _, _, user = record
    _require_permission(request, user, "workflows.read")

    normalized_format = _validate_format(format_name)
    manager = _manager(request)

    try:
        workflow = manager.get(name)
        result = _workflow_payload(workflow, manager, normalized_format)
    except Exception as exc:
        if isinstance(exc, (WorkflowNotFoundError, WorkflowNotMatchError)):
            raise _translate_workflow_error(exc) from exc
        raise

    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/validate")
def validate_workflow(
    payload: WorkflowDefinitionRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, object]:
    """Validate a supplied workflow without saving it (authoring or starting a run)."""

    _, _, user = record
    _require_any_permission(request, user, "workflows.write", "workflows.execute")

    normalized_format = _validate_format(payload.format)
    manager = _manager(request)

    for path in _definition_file(payload.definition, normalized_format):
        try:
            workflow = manager.load(path)
            result = _workflow_payload(workflow, manager, normalized_format)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    response.headers["Cache-Control"] = "no-store"
    return {"valid": True, "workflow": result}


@router.post("", status_code=201)
def create_workflow(
    payload: WorkflowDefinitionRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, object]:
    """Validate and register a new workflow."""

    _, _, user = record
    _require_permission(request, user, "workflows.write")

    normalized_format = _validate_format(payload.format)
    manager = _manager(request)

    for path in _definition_file(payload.definition, normalized_format):
        try:
            candidate = manager.load(path)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _check_plugin_access(request, user, candidate)
        try:
            workflow = manager.add(path)
            result = _workflow_payload(workflow, manager, normalized_format)
            _clear_drafts(request, workflow.name)
        except Exception as exc:
            if isinstance(exc, WorkflowAlreadyExistsError):
                raise _translate_workflow_error(exc) from exc
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    response.headers["Cache-Control"] = "no-store"
    return result


@router.put("/{name}")
def update_workflow(
    name: str,
    payload: WorkflowDefinitionRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, object]:
    """Validate and replace an existing registered workflow."""

    _, _, user = record
    _require_permission(request, user, "workflows.write")

    normalized_format = _validate_format(payload.format)
    manager = _manager(request)

    for path in _definition_file(payload.definition, normalized_format):
        try:
            candidate = manager.load(path)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _check_plugin_access(request, user, candidate)
        previous = _current(manager, name)
        _bump_if_unchanged_version(manager, name, path, normalized_format)
        try:
            workflow = manager.replace(name, path)
            result = _workflow_payload(workflow, manager, normalized_format)
            _clear_drafts(request, name)
            # Keep the replaced version so it can be compared and restored.
            if manager.serialize(workflow, "json") != manager.serialize(previous, "json"):
                _history(request).record(
                    name,
                    previous.version,
                    manager.serialize(previous, "json"),
                    user=user.username,
                )
        except Exception as exc:
            if isinstance(
                exc,
                (WorkflowNotFoundError, WorkflowNotMatchError),
            ):
                raise _translate_workflow_error(exc) from exc
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    response.headers["Cache-Control"] = "no-store"
    return result


@router.delete("/{name}")
def delete_workflow(
    name: str,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, object]:
    """Remove a registered workflow."""

    _, _, user = record
    _require_permission(request, user, "workflows.delete")

    manager = _manager(request)

    try:
        manager.remove(name)
    except WorkflowNotFoundError as exc:
        raise _translate_workflow_error(exc) from exc

    _history(request).forget(name)
    _clear_drafts(request, name)

    response.headers["Cache-Control"] = "no-store"
    return {"deleted": True, "name": name}


# ----------------------------------------------------------------------
# History
# ----------------------------------------------------------------------


@router.get("/{name}/history")
def workflow_history(
    name: str,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, object]:
    """Earlier versions kept before each change (the last five)."""

    _, _, user = record
    _require_permission(request, user, "workflows.read")
    current = _current(_manager(request), name)

    response.headers["Cache-Control"] = "no-store"
    return {"current_version": current.version, "items": _history(request).list(name)}


@router.get("/{name}/history/{entry_id}")
def workflow_history_entry(
    name: str,
    entry_id: int,
    request: Request,
    response: Response,
    format: str = Query("yaml"),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, object]:
    """One kept version's definition, in the requested format."""

    _, _, user = record
    _require_permission(request, user, "workflows.read")
    normalized_format = _validate_format(format)
    manager = _manager(request)

    entry = _history(request).get(name, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="That version is no longer kept.")

    definition, shown = entry["content"], "json"
    for path in _definition_file(definition, "json"):
        try:
            definition = manager.serialize(manager.load(path), normalized_format)
            shown = normalized_format
        except Exception:  # noqa: BLE001 - e.g. a plugin it used is gone; show it as kept
            pass

    response.headers["Cache-Control"] = "no-store"
    return {
        "id": entry["id"],
        "version": entry["version"],
        "reason": entry["reason"],
        "created_by": entry["created_by"],
        "created_at": entry["created_at"],
        "format": shown,
        "definition": definition,
    }


@router.post("/{name}/history/{entry_id}/restore")
def restore_workflow_version(
    name: str,
    entry_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, object]:
    """
    Make a kept version current again. The current version is kept first,
    and the restored one gets the next version number.
    """

    _, _, user = record
    _require_permission(request, user, "workflows.write")
    manager = _manager(request)
    history = _history(request)

    entry = history.get(name, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="That version is no longer kept.")
    current = _current(manager, name)

    for path in _definition_file(entry["content"], "json"):
        try:
            restored = manager.load(path)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"Version {entry['version']} cannot be restored: {exc}"
            ) from exc
        if restored.name != name:
            raise HTTPException(status_code=422, detail="That version belongs to another workflow.")
        _check_plugin_access(request, user, restored)

        restored = dataclasses.replace(restored, version=bump_version(current.version))
        path.write_text(manager.serialize(restored, "json"), encoding="utf-8")

        history.record(
            name,
            current.version,
            manager.serialize(current, "json"),
            user=user.username,
            reason="restore",
        )
        try:
            workflow = manager.replace(name, path)
        except Exception as exc:
            raise _translate_workflow_error(exc) from exc
        result = _workflow_payload(workflow, manager, "yaml")

    response.headers["Cache-Control"] = "no-store"
    return {**result, "restored_from": entry["version"]}
