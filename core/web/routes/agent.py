"""
API for node agents. Agents authenticate with their node token
(`Authorization: Bearer ...`), not with a browser session, so these
endpoints take no cookies and need no CSRF token.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/agent", tags=["agent"])


class HeartbeatRequest(BaseModel):
    version: str = ""
    metrics: Dict[str, Any] = Field(default_factory=dict)
    info: Dict[str, Any] = Field(default_factory=dict)
    running: List[str] = Field(default_factory=list)


class ClaimRequest(BaseModel):
    wait: float = Field(default=20, ge=0, le=30)


class ReportRequest(BaseModel):
    events: List[Dict[str, Any]] = Field(default_factory=list, max_length=2000)
    log: str = Field(default="", max_length=1_000_000)
    state: str = ""
    exit_code: Optional[int] = None
    final: bool = False


def _dispatcher(request: Request):
    from lib.nodes.dispatch import NodeDispatcher

    context = request.app.state.entropy_context
    if context is None or context.database_manager is None:
        raise HTTPException(status_code=503, detail="Main node unavailable.")
    return NodeDispatcher(context)


def _node(request: Request) -> Dict[str, Any]:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Node token required.")

    node = _dispatcher(request).authenticate(token.strip())
    if node is None:
        raise HTTPException(status_code=401, detail="Unknown or revoked node token.")
    return node


@router.post("/heartbeat")
def heartbeat(
    payload: HeartbeatRequest,
    request: Request,
    node: Dict[str, Any] = Depends(_node),
) -> Dict[str, Any]:
    """Record metrics; reply with runs to stop."""

    return _dispatcher(request).heartbeat(node, payload.model_dump())


@router.post("/jobs/claim")
async def claim(
    payload: ClaimRequest,
    request: Request,
    node: Dict[str, Any] = Depends(_node),
) -> Dict[str, Any]:
    """
    Take the next run queued for this node (long poll). The poll ends
    when the agent disconnects, so a stopped agent never takes a run.
    """

    dispatcher = _dispatcher(request)
    deadline = time.monotonic() + payload.wait

    while True:
        job = await run_in_threadpool(dispatcher.claim, node, 0)
        if job is not None or time.monotonic() >= deadline:
            return {"job": job}
        if await request.is_disconnected():
            return {"job": None}
        await asyncio.sleep(1)


@router.post("/jobs/{job_id}/events")
def report(
    job_id: int,
    payload: ReportRequest,
    request: Request,
    node: Dict[str, Any] = Depends(_node),
) -> Dict[str, Any]:
    """Events, console output and state of a run on this node."""

    try:
        return _dispatcher(request).report(node, job_id, payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/extensions")
def extension_bundle(
    name: str,
    request: Request,
    version: str = "",
    node: Dict[str, Any] = Depends(_node),
) -> Response:
    """
    The wheels of the newest installed extension version that fits
    `version` (a version or range), for a plugin a node installs.
    """

    from lib.extensions.resolver import fits, specifier

    manager = getattr(request.app.state.entropy_context, "extension_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Extensions are unavailable.")
    try:
        spec = specifier(version or None)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid version requirement.") from None
    from packaging.version import Version

    candidates = sorted(
        (entry for entry in manager.store.versions(name) if fits(entry["version"], spec)),
        key=lambda entry: Version(entry["version"]),
        reverse=True,
    )
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"The server has no extension {name} {version or ''}; install it there first.",
        )
    chosen = candidates[0]
    return Response(
        content=manager.bundle(chosen["name"], chosen["version"]),
        media_type="application/gzip",
        headers={
            "X-Entropy-Extension": chosen["name"],
            "X-Entropy-Version": chosen["version"],
            "Cache-Control": "no-store",
        },
    )


@router.get("/plugins/{qualified_name}")
def plugin_bundle(
    qualified_name: str,
    request: Request,
    node: Dict[str, Any] = Depends(_node),
) -> Response:
    """An installed plugin as an archive, for a run that needs it."""

    from lib.nodes.packaging import plugin_bundle as bundle

    manager = request.app.state.entropy_context.plugin_manager
    if manager is None or "." not in qualified_name or not manager.exists(qualified_name):
        raise HTTPException(status_code=404, detail="Plugin not installed.")

    data, digest = bundle(manager.get(qualified_name).path)
    return Response(
        content=data,
        media_type="application/gzip",
        headers={"X-Entropy-Digest": digest, "Cache-Control": "no-store"},
    )
