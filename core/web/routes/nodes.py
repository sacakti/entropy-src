"""
Execution nodes: list, inspect metrics (JSON, history and Prometheus
text format) and enable/disable nodes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

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
            metrics["agent_up"] = node["agent_up"]
            metrics["running_jobs"] = node["running_jobs"]
        node["metrics"] = metrics
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

    node = _store(request).update(name, description=payload.description, enabled=payload.enabled)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{name}' does not exist.")

    return {"node": _with_metrics(request, [node])[0]}
