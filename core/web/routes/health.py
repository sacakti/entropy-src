from __future__ import annotations

"""Health endpoint for the Entropy web application."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/health", tags=["system"])
async def health(request: Request) -> dict[str, str | bool]:
    """Return process health and whether Entropy context initialization completed."""

    context = getattr(request.app.state, "entropy_context", None)

    return {
        "status": "ok",
        "application": "entropy",
        "initialized": context is not None,
    }
