"""
Triggers: run a workflow or plugin when a webhook is called or a queue message
arrives. Here they are listed, changed and fired by hand; the webhook itself is
core/web/routes/hooks.py and the queue listener lib/triggers/stomp.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import current_project
from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.schedules import _check_target
from core.web.routes.workflows import _require_permission
from lib.models.session import Session
from lib.models.users import User
from lib.triggers.fire import fire_trigger
from lib.triggers.store import TriggerError, TriggerStore

router = APIRouter(prefix="/api/triggers", tags=["triggers"])

SessionRecord = Tuple[Session, str, User]


class TriggerRequest(BaseModel):
    name: str = Field(max_length=80)
    description: str = Field(default="", max_length=500)
    source: str
    kind: str
    target: str = Field(max_length=300)
    node: str = "local"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    use_payload: bool = True
    destination: Optional[str] = Field(default=None, max_length=210)
    enabled: bool = True


class TriggerPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    source: Optional[str] = None
    kind: Optional[str] = None
    target: Optional[str] = Field(default=None, max_length=300)
    node: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    use_payload: Optional[bool] = None
    destination: Optional[str] = Field(default=None, max_length=210)
    enabled: Optional[bool] = None


class FireRequest(BaseModel):
    payload: str = Field(default="", max_length=1024 * 1024)


class IdsRequest(BaseModel):
    ids: List[int] = Field(default_factory=list, max_length=500)


def _store(request: Request) -> TriggerStore:
    context = request.app.state.entropy_context
    if context is None or context.database_manager is None:
        raise HTTPException(status_code=503, detail="Trigger service unavailable.")
    return TriggerStore(context.database_manager.connection)


def _trigger(request: Request, user: User, trigger_id: int, permission: str) -> Dict[str, Any]:
    """The trigger, if the user has `permission` in its project."""

    trigger = _store(request).get(trigger_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found.")
    _require_permission(request, user, permission, trigger["project_id"])
    return trigger


def _http(exc: TriggerError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


def hook_base(request: Request) -> str:
    """Where callers reach Entropy: the public address if set, else this request's."""

    from lib.system.settings import settings_for

    public = settings_for(request.app.state.entropy_context).get("general")["public_url"]
    return (public or str(request.base_url)).rstrip("/")


def _shown(request: Request, trigger: Dict[str, Any]) -> Dict[str, Any]:
    shown = dict(trigger)
    shown["hook_url"] = (
        f"{hook_base(request)}/api/hooks/{trigger['hook_key']}"
        if trigger["source"] == "webhook"
        else None
    )
    return shown


@router.get("")
def list_triggers(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    project = current_project(request, user)
    _require_permission(request, user, "triggers.list", project["id"])
    store = _store(request)
    response.headers["Cache-Control"] = "no-store"
    return {
        "items": [_shown(request, item) for item in store.list(project["id"])],
        "listener": store.listener_status(),
    }


@router.get("/{trigger_id}")
def get_trigger(
    trigger_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    trigger = _trigger(request, user, trigger_id, "triggers.list")
    response.headers["Cache-Control"] = "no-store"
    return {"trigger": _shown(request, trigger), "runs": _store(request).runs(trigger_id)}


@router.post("", status_code=201, dependencies=[Depends(verify_csrf)])
def create_trigger(
    payload: TriggerRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """The new trigger, and for a webhook its secret token: shown this once."""

    _, _, user = record
    project = current_project(request, user)
    _require_permission(request, user, "triggers.manage", project["id"])
    data = payload.model_dump()
    _check_target(request, user, data, project["id"])
    try:
        created = _store(request).create(data, int(user.id or 0), user.username, project["id"])
    except TriggerError as exc:
        raise _http(exc) from exc
    return {"trigger": _shown(request, created["trigger"]), "token": created["token"]}


@router.patch("/{trigger_id}", dependencies=[Depends(verify_csrf)])
def update_trigger(
    trigger_id: int,
    payload: TriggerPatch,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    current = _trigger(request, user, trigger_id, "triggers.manage")
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    if "kind" in changes or "target" in changes:
        _check_target(request, user, {**current, **changes}, current["project_id"])
    try:
        updated = _store(request).update(trigger_id, changes)
    except TriggerError as exc:
        raise _http(exc) from exc
    return {"trigger": _shown(request, updated["trigger"]), "token": updated["token"]}


@router.post("/{trigger_id}/token", dependencies=[Depends(verify_csrf)])
def new_token(
    trigger_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """A new secret token for a webhook; callers using the old one are refused."""

    _, _, user = record
    trigger = _trigger(request, user, trigger_id, "triggers.manage")
    if trigger["source"] != "webhook":
        raise HTTPException(status_code=422, detail="Only webhook triggers have a token.")
    token = _store(request).new_token(trigger_id)
    return {"trigger": _shown(request, _store(request).get(trigger_id) or {}), "token": token}


@router.post("/{trigger_id}/fire", dependencies=[Depends(verify_csrf)])
def fire_now(
    trigger_id: int,
    payload: FireRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Fire the trigger now, as the current user, with a payload to try it with."""

    _, _, user = record
    trigger = _trigger(request, user, trigger_id, "triggers.manage")
    store = _store(request)
    run = fire_trigger(
        request.app.state.entropy_context,
        store,
        trigger,
        payload_text=payload.payload,
        source="manual",
        caller=f"Fired by {user.username}",
        user=user,
    )
    return {"run": run}


@router.post("/delete", dependencies=[Depends(verify_csrf)])
def delete_triggers(
    payload: IdsRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    for trigger_id in payload.ids:
        _trigger(request, user, trigger_id, "triggers.delete")
    return {"deleted": _store(request).delete(payload.ids)}
