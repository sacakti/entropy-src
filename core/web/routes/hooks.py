"""
Webhooks: POST /api/hooks/<hook key> runs a webhook trigger's workflow or plugin.

No Entropy sign-in: the caller sends the trigger's secret token in the
X-Entropy-Token header (or ?token=). The body, up to 1 MB, is the payload: a
JSON object's fields override the trigger's parameters.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from lib.triggers.fire import fire_trigger
from lib.triggers.store import TriggerStore

router = APIRouter(prefix="/api/hooks", tags=["triggers"])

TOKEN_HEADER = "X-Entropy-Token"
MAX_PAYLOAD = 1024 * 1024
# One answer for an unknown hook and a wrong token: nothing tells which hooks exist.
REFUSED = "Unknown hook, or a wrong or missing token."


@router.post("/{hook_key}", status_code=202)
async def call_hook(
    hook_key: str,
    request: Request,
    token: Optional[str] = Query(default=None, max_length=200),
) -> JSONResponse:
    context = request.app.state.entropy_context
    if context is None or context.database_manager is None:
        raise HTTPException(status_code=503, detail="Trigger service unavailable.")

    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > MAX_PAYLOAD:
        raise HTTPException(status_code=413, detail="The payload is larger than 1 MB.")
    body = await request.body()
    if len(body) > MAX_PAYLOAD:
        raise HTTPException(status_code=413, detail="The payload is larger than 1 MB.")

    store = TriggerStore(context.database_manager.connection)
    trigger = store.by_hook_key(hook_key) if len(hook_key) <= 64 else None
    secret = request.headers.get(TOKEN_HEADER) or token or ""
    if trigger is None or not store.check_token(trigger["id"], secret):
        raise HTTPException(status_code=401, detail=REFUSED)
    if not trigger["enabled"]:
        raise HTTPException(status_code=409, detail="This trigger is paused.")

    caller = request.client.host if request.client else None
    run = await run_in_threadpool(
        fire_trigger,
        context,
        store,
        trigger,
        payload_text=body.decode("utf-8", "replace"),
        source="webhook",
        caller=f"Webhook from {caller}" if caller else "Webhook",
    )
    if run["error"]:
        return JSONResponse(
            status_code=422,
            content={"accepted": False, "detail": run["error"], "firing_id": run["id"]},
        )
    return JSONResponse(
        status_code=202,
        content={"accepted": True, "run_id": run["job_id"], "firing_id": run["id"]},
    )
