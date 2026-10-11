
"""
Dashboard summary and workflow execution API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from core.web.routes.auth import _current_session
from core.web.routes.workflows import _require_permission
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

SessionRecord = tuple[Session, str, User]

ACTIVE_STATES = {"queued", "starting", "running", "paused"}
TERMINAL_STATES = {"completed", "failed", "cancelled"}
ALL_STATES = (
    "queued",
    "starting",
    "running",
    "paused",
    "completed",
    "failed",
    "cancelled",
)
ACTIVE_LIMIT = 8
RECENT_LIMIT = 8


def _timestamp(value: datetime | None) -> str | None:
    """Serialize a job timestamp as ISO 8601."""
    return value.isoformat() if value is not None else None


def _job_payload(job: Any) -> dict[str, Any]:
    """Return only fields required by the dashboard."""
    return {
        "id": job.id,
        "execution_id": job.execution_id,
        "workflow": job.workflow,
        "state": job.state.value,
        "created_at": _timestamp(job.created_at),
        "started_at": _timestamp(job.started_at),
        "finished_at": _timestamp(job.finished_at),
        "exit_code": job.exit_code,
    }


@router.get("")
def get_dashboard(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """Return workflow execution summary for the authenticated user."""
    _, _, user = record
    _require_permission(request, user, "workflows.list")

    context = request.app.state.entropy_context
    job_manager = context.workflow_job_manager

    if job_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Workflow job service unavailable.",
        )

    # Repository.list() is ordered by descending ID, newest first.
    jobs = job_manager.list()

    counts = {state: 0 for state in ALL_STATES}
    for job in jobs:
        counts[job.state.value] += 1

    active_jobs = [
        job for job in jobs
        if job.state.value in ACTIVE_STATES
    ][:ACTIVE_LIMIT]

    recent_jobs = [
        job for job in jobs
        if job.state.value in TERMINAL_STATES
    ][:RECENT_LIMIT]

    response.headers["Cache-Control"] = "no-store"

    return {
        "summary": {
            "total": len(jobs),
            **counts,
        },
        "active_executions": [
            _job_payload(job) for job in active_jobs
        ],
        "recent_executions": [
            _job_payload(job) for job in recent_jobs
        ],
    }
