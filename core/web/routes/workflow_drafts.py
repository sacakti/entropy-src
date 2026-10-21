"""
Workflow drafts: "Save with errors" in the workflow builder.

A draft keeps a definition that does not validate yet. It is listed with
the workflows, opens in the builder, and cannot run. Saving the workflow
for real removes the draft.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import (
    MAX_DEFINITION_LENGTH,
    _definition_file,
    _manager,
    _require_permission,
)
from lib.models.session import Session
from lib.models.users import User
from lib.workflow.drafts import WorkflowDrafts

router = APIRouter(prefix="/api/workflow-drafts", tags=["workflows"])

SessionRecord = Tuple[Session, str, User]


class DraftRequest(BaseModel):
    id: Optional[int] = None
    # The registered workflow this draft edits; None for a new workflow.
    workflow: Optional[str] = Field(default=None, max_length=200)
    definition: str = Field(max_length=MAX_DEFINITION_LENGTH)
    format: str = "json"
    # Problems the builder found; the server adds its own validation result.
    errors: List[str] = Field(default_factory=list, max_length=200)


def _drafts(request: Request) -> WorkflowDrafts:
    context = request.app.state.entropy_context
    if context.database_manager is None:
        raise HTTPException(status_code=503, detail="Database is unavailable.")
    return WorkflowDrafts(context.database_manager.connection)


def _title(definition: str, workflow: Optional[str]) -> str:
    """The workflow's name if it can be read from the text, even when invalid."""

    try:
        parsed = json.loads(definition)
        if isinstance(parsed, dict) and str(parsed.get("name") or "").strip():
            return str(parsed["name"]).strip()[:200]
    except ValueError:
        pass
    match = re.search(r"^name:\s*['\"]?([^'\"\n#]+)", definition, re.MULTILINE)
    if match and match.group(1).strip():
        return match.group(1).strip()[:200]
    return workflow or "Untitled workflow"


def _server_errors(request: Request, definition: str, format_name: str) -> List[str]:
    if not definition.strip():
        return ["The definition is empty."]
    manager = _manager(request)
    try:
        for path in _definition_file(definition, format_name):
            manager.load(path)
    except HTTPException as exc:
        return [str(exc.detail)]
    except Exception as exc:  # noqa: BLE001 - any validation failure is the draft's problem
        # The validator names the temporary file it read; that means nothing here.
        return [re.sub(r"^Unable to load workflow '[^']*':\s*", "", str(exc))]
    return []


@router.get("")
def list_drafts(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, object]:
    _, _, user = record
    _require_permission(request, user, "workflows.read")
    response.headers["Cache-Control"] = "no-store"
    return {"items": _drafts(request).list()}


@router.get("/{draft_id}")
def get_draft(
    draft_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, object]:
    _, _, user = record
    _require_permission(request, user, "workflows.read")
    draft = _drafts(request).get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    response.headers["Cache-Control"] = "no-store"
    return draft


@router.post("", dependencies=[Depends(verify_csrf)])
def save_draft(
    payload: DraftRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, object]:
    """Save a definition as it is, with its problems listed."""

    _, _, user = record
    _require_permission(request, user, "workflows.write")
    format_name = payload.format.strip().lower()
    if format_name not in ("json", "yaml"):
        raise HTTPException(status_code=422, detail="Format must be json or yaml.")
    if payload.workflow:
        # Only drafts of workflows that exist; a new workflow has none.
        try:
            _manager(request).get(payload.workflow)
        except Exception:  # noqa: BLE001 - not found or unreadable
            raise HTTPException(
                status_code=404, detail=f"Workflow '{payload.workflow}' not found."
            ) from None

    errors = list(
        dict.fromkeys([*payload.errors, *_server_errors(request, payload.definition, format_name)])
    )
    draft = _drafts(request).save(
        draft_id=payload.id,
        workflow=payload.workflow,
        title=_title(payload.definition, payload.workflow),
        format=format_name,
        definition=payload.definition,
        errors=[str(item)[:1000] for item in errors],
        user=user.username,
    )
    response.headers["Cache-Control"] = "no-store"
    return draft


@router.delete("/{draft_id}", dependencies=[Depends(verify_csrf)])
def delete_draft(
    draft_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, object]:
    _, _, user = record
    _require_permission(request, user, "workflows.write")
    if not _drafts(request).delete(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found.")
    return {"deleted": True}
