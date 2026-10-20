"""
Execution nodes: list, inspect metrics (JSON, history and Prometheus
text format) and enable/disable nodes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import _require_permission
from lib.models.session import Session
from lib.models.users import User
from lib.runs.nodes import LocalMetrics, NodeStore, agent_up, exposition
from lib.runs.store import LOCAL_NODE, RunStore

router = APIRouter(prefix="/api/nodes", tags=["nodes"])

SessionRecord = Tuple[Session, str, User]

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class NodeUpdateRequest(BaseModel):
    description: Optional[str] = None
    enabled: Optional[bool] = None
    max_jobs: Optional[int] = Field(default=None, ge=1, le=64)


class Credentials(BaseModel):
    """SSH credentials for one setup; never stored."""

    auth: str = Field(default="password", pattern="^(password|key|server)$")
    password: Optional[str] = Field(default=None, max_length=1024)
    private_key: Optional[str] = Field(default=None, max_length=32768)
    passphrase: Optional[str] = Field(default=None, max_length=1024)
    forget_host_key: bool = False


class NodeSetupRequest(Credentials):
    name: str = Field(max_length=63)
    host: str = Field(max_length=253)
    port: int = 22
    ssh_user: str = Field(max_length=64)
    server_url: str = Field(max_length=500)
    verify_tls: bool = True
    ca_cert: Optional[str] = Field(default=None, max_length=65536)
    python: str = "auto"
    install_dir: str = Field(default="~/.entropy-agent", max_length=255)
    max_jobs: int = 2
    description: str = Field(default="", max_length=500)


class NodeRemoveRequest(Credentials):
    """Remove a node; with `uninstall`, also remove the agent over SSH."""

    uninstall: bool = False


def _provision_request(payload: Credentials, **values: Any):
    from lib.nodes.provision import ProvisionRequest

    if payload.auth == "password" and not payload.password:
        raise HTTPException(status_code=422, detail="Enter the SSH password.")
    if payload.auth == "key" and not (payload.private_key or "").strip():
        raise HTTPException(status_code=422, detail="Paste the private key.")

    return ProvisionRequest(
        password=payload.password if payload.auth == "password" else None,
        private_key=payload.private_key if payload.auth == "key" else None,
        passphrase=(payload.passphrase or None) if payload.auth == "key" else None,
        forget_host_key=payload.forget_host_key,
        **values,
    )


def _notify_done(request: Request, user: User, node: str, action: str):
    context = _context(request)

    def done(error: Optional[str]) -> None:
        from lib.database.repositories.notifications import notify_user

        if user.id is None:
            return
        verb = "set up" if action == "install" else "removed"
        notify_user(
            context,
            user.id,
            f"Node '{node}' {verb}" if not error else f"Node '{node}' could not be {verb}",
            "It is ready to run workflows." if not error and action == "install" else (error or ""),
            "success" if not error else "error",
            "nodes",
        )

    return done


def _context(request: Request):
    context = request.app.state.entropy_context
    if context is None or context.database_manager is None:
        raise HTTPException(status_code=503, detail="Node service unavailable.")
    return context


def _local_metrics(request: Request) -> Dict[str, Any]:
    """Latest local sample from the background sampler, else read now."""

    background = getattr(request.app.state, "runs_background", None)
    latest = getattr(background, "latest_local", None)
    if latest:
        return dict(latest)

    reader = getattr(request.app.state, "local_metrics_reader", None)
    if reader is None:
        reader = LocalMetrics(Path(_context(request).bootstrap.home))
        request.app.state.local_metrics_reader = reader
    return reader.collect()


def _with_metrics(request: Request, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    runs = RunStore(_context(request).database_manager.connection)
    for node in nodes:
        node["agent_up"] = agent_up(node)
        node["running_jobs"] = runs.running_on(node["name"])
        metrics = None
        if node["kind"] == "local":
            metrics = _local_metrics(request)
        elif node.get("last_metrics"):
            # The agent's latest heartbeat; stale when the agent is down.
            metrics = dict(node["last_metrics"])
        if metrics is not None:
            metrics["agent_up"] = node["agent_up"]
            metrics["running_jobs"] = node["running_jobs"]
        node["metrics"] = metrics
        node.pop("last_metrics", None)
    return nodes


def _store(request: Request) -> NodeStore:
    return NodeStore(_context(request).database_manager.connection)


@router.get("")
def list_nodes(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Nodes with their current metrics. Anyone who can start runs may list them."""

    _, _, user = record
    authorization = _context(request).authorization
    if (
        user.id is None
        or authorization is None
        or not any(
            authorization.has_permission(user.id, permission)
            for permission in ("nodes.list", "workflows.start", "plugins.run", "schedules.manage")
        )
    ):
        raise HTTPException(status_code=403, detail="Permission denied.")

    response.headers["Cache-Control"] = "no-store"
    return {"items": _with_metrics(request, _store(request).list())}


@router.get("/metrics", response_class=PlainTextResponse)
def all_metrics(
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> PlainTextResponse:
    """Every node in the Prometheus text exposition format."""

    _, _, user = record
    _require_permission(request, user, "nodes.list")

    nodes = _with_metrics(request, _store(request).list())
    return PlainTextResponse(
        exposition(nodes),
        media_type=PROMETHEUS_CONTENT_TYPE,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{name}")
def get_node(
    name: str,
    request: Request,
    response: Response,
    hours: float = Query(1, gt=0, le=168),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """One node with its metrics and sample history."""

    _, _, user = record
    _require_permission(request, user, "nodes.list")

    store = _store(request)
    node = store.get(name)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{name}' does not exist.")

    response.headers["Cache-Control"] = "no-store"
    return {
        "node": _with_metrics(request, [node])[0],
        "history": store.history(name, hours),
    }


@router.get("/{name}/metrics", response_class=PlainTextResponse)
def node_metrics(
    name: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> PlainTextResponse:
    """One node in the Prometheus text exposition format."""

    _, _, user = record
    _require_permission(request, user, "nodes.list")

    node = _store(request).get(name)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{name}' does not exist.")

    return PlainTextResponse(
        exposition(_with_metrics(request, [node])),
        media_type=PROMETHEUS_CONTENT_TYPE,
        headers={"Cache-Control": "no-store"},
    )


@router.patch("/{name}", dependencies=[Depends(verify_csrf)])
def update_node(
    name: str,
    payload: NodeUpdateRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _, _, user = record
    _require_permission(request, user, "nodes.manage")

    if name == LOCAL_NODE and payload.enabled is False:
        raise HTTPException(
            status_code=409,
            detail="The main node cannot be disabled; it runs schedules and stores Entropy data.",
        )

    node = _store(request).update(
        name, description=payload.description, enabled=payload.enabled, max_jobs=payload.max_jobs
    )
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{name}' does not exist.")

    return {"node": _with_metrics(request, [node])[0]}


# ----------------------------------------------------------------------
# Remote nodes
# ----------------------------------------------------------------------


@router.post("", status_code=202, dependencies=[Depends(verify_csrf)])
def add_node(
    payload: NodeSetupRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Set up a node over SSH; follow progress at /provisioning/{id}."""

    return _setup(payload, request, record, existing=False)


@router.post("/{name}/setup", status_code=202, dependencies=[Depends(verify_csrf)])
def setup_node(
    name: str,
    payload: NodeSetupRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Set an existing node up again (new token, updated runtime)."""

    if payload.name != name:
        raise HTTPException(status_code=422, detail="A node cannot be renamed.")
    return _setup(payload, request, record, existing=True)


def _setup(
    payload: NodeSetupRequest,
    request: Request,
    record: SessionRecord,
    *,
    existing: bool,
) -> Dict[str, Any]:
    from lib.nodes.provision import Provisioner, ProvisionError

    _, _, user = record
    _require_permission(request, user, "nodes.manage")

    node = _store(request).get(payload.name)
    if existing and node is None:
        raise HTTPException(status_code=404, detail=f"Node '{payload.name}' does not exist.")
    if not existing and node is not None:
        raise HTTPException(
            status_code=409, detail=f"A node named '{payload.name}' already exists."
        )

    provision = _provision_request(
        payload,
        name=payload.name.strip(),
        host=payload.host.strip(),
        port=payload.port,
        ssh_user=payload.ssh_user.strip(),
        server_url=payload.server_url.strip(),
        verify_tls=payload.verify_tls,
        ca_cert=payload.ca_cert,
        python=payload.python,
        install_dir=payload.install_dir.strip(),
        max_jobs=payload.max_jobs,
        description=payload.description.strip(),
    )
    # The request body (and its secrets) is no longer referenced past here.
    payload.password = payload.private_key = payload.passphrase = None

    try:
        record_id = Provisioner(_context(request)).start(
            provision, user, on_done=_notify_done(request, user, provision.name, "install")
        )
    except ProvisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"provisioning_id": record_id, "node": provision.name}


@router.get("/provisioning/{record_id}")
def provisioning(
    record_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    from lib.nodes.provision import Provisioner

    _, _, user = record
    _require_permission(request, user, "nodes.list")

    result = Provisioner(_context(request)).record(record_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Setup record not found.")
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/{name}/provisioning")
def latest_provisioning(
    name: str,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    from lib.nodes.provision import Provisioner

    _, _, user = record
    _require_permission(request, user, "nodes.list")

    response.headers["Cache-Control"] = "no-store"
    return {"provisioning": Provisioner(_context(request)).latest(name)}


@router.post("/{name}/remove", dependencies=[Depends(verify_csrf)])
def remove_node(
    name: str,
    payload: NodeRemoveRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """
    Remove a node. Its token is revoked at once, so its agent stops; with
    `uninstall`, the agent's files are also removed over SSH.
    """

    from lib.nodes.provision import Provisioner, ProvisionError

    _, _, user = record
    _require_permission(request, user, "nodes.manage")

    store = _store(request)
    node = store.get(name)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{name}' does not exist.")
    if node["kind"] == "local":
        raise HTTPException(status_code=409, detail="The main node cannot be removed.")

    if not payload.uninstall:
        store.set_token(name, None)
        store.delete(name)
        return {"removed": True, "node": name}

    provision = _provision_request(
        payload,
        name=name,
        host=node["host"],
        port=node["port"],
        ssh_user=node["ssh_user"],
        server_url=node.get("server_url") or "https://localhost",
        install_dir=node.get("install_dir") or "~/.entropy-agent",
    )
    payload.password = payload.private_key = payload.passphrase = None
    # Revoke first: the agent must stop even if the SSH removal fails.
    store.set_token(name, None)

    try:
        record_id = Provisioner(_context(request)).start(
            provision,
            user,
            action="uninstall",
            on_done=_notify_done(request, user, name, "uninstall"),
        )
    except ProvisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"removed": False, "provisioning_id": record_id, "node": name}
