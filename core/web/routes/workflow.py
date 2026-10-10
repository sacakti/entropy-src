
"""
Authenticated workflow management API.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from core.web.routes.auth import _current_session, verify_csrf
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
