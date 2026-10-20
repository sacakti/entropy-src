
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
    _require_permission(request, user, "workflows.list")

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
    _require_permission(request, user, "workflows.list")

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
    _require_permission(request, user, "workflows.list")

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
    """Validate a supplied workflow without saving it."""

    _, _, user = record
    _require_permission(request, user, "workflows.add")

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
    _require_permission(request, user, "workflows.add")

    normalized_format = _validate_format(payload.format)
    manager = _manager(request)

    for path in _definition_file(payload.definition, normalized_format):
        try:
            workflow = manager.add(path)
            result = _workflow_payload(workflow, manager, normalized_format)
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
    _require_permission(request, user, "workflows.edit")

    normalized_format = _validate_format(payload.format)
    manager = _manager(request)

    for path in _definition_file(payload.definition, normalized_format):
        _bump_if_unchanged_version(manager, name, path, normalized_format)
        try:
            workflow = manager.replace(name, path)
            result = _workflow_payload(workflow, manager, normalized_format)
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
    _require_permission(request, user, "workflows.edit")

    manager = _manager(request)

    try:
        manager.remove(name)
    except WorkflowNotFoundError as exc:
        raise _translate_workflow_error(exc) from exc

    response.headers["Cache-Control"] = "no-store"
    return {"deleted": True, "name": name}
