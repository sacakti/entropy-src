"""
Audit middleware: records every change made through the web API.

Browsers and the `ent` command line both reach Entropy through these
routes, so recording here covers them all without touching each route:

- every POST, PUT, PATCH and DELETE under /api (allowed, refused or failed);
- downloads and exports (files, backups, reports, artifact contents);
- sign-ins (including failed ones) are recorded by the auth routes.

Request bodies are never stored: they can hold passwords and secrets. Only
the name of what was created or changed (a "name", "username", "title" or
"key" field) is kept, next to the route's own identifiers.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool

from lib.audit.actions import describe, target

LOGGER = logging.getLogger("entropy.audit")
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
# Reads worth auditing: files and data leaving Entropy.
AUDITED_READS = re.compile(
    r"/(download|export[^/]*|report[^/]*|backups/[^/]+|ent\.pyz|entries/content)$|/bulk-download$"
)
# Noise, or recorded by the route itself with more detail.
SKIPPED = {
    ("POST", "/api/auth/keepalive"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/token"),
    ("POST", "/api/agent/heartbeat"),
    ("POST", "/api/version/notes/seen"),
}
# Body fields that name what was created or changed (never values like passwords).
NAME_FIELDS = ("name", "username", "title", "key", "workflow_name", "target_environment")
MAX_BODY = 256 * 1024
# Old entries are removed at most this often (seconds), as entries are written.
PURGE_EVERY = 3600
_last_purge = 0.0


def should_audit(method: str, path: str) -> bool:
    if not path.startswith("/api/") or (method, path) in SKIPPED:
        return False
    if path.startswith("/api/notifications") and path.endswith("/read"):
        return False
    if path.startswith("/api/preferences"):
        # A user's own look and layout (theme, wallpaper, dashboard), saved as they change it.
        return False
    if path.startswith("/api/agent/"):
        # Node agents report in continuously; their jobs are audited where they start.
        return False
    return method in MUTATING or (method == "GET" and bool(AUDITED_READS.search(path)))


def _body_name(raw: bytes, content_type: str) -> Optional[str]:
    if not raw or len(raw) > MAX_BODY or "json" not in content_type:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for field in NAME_FIELDS:
        value = data.get(field)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()[:200]
    return None


def _who(request: Request) -> Tuple[Optional[int], Optional[str], str]:
    """(user id, username, source) of the caller, read before the route runs (e.g. sign-out)."""

    from core.web.routes.auth import SESSION_COOKIE, bearer_token

    store = getattr(request.app.state, "web_session_store", None)
    token = bearer_token(request)
    source = "cli" if token else "web"
    if store is None:
        return None, None, source
    record = store.get(token or request.cookies.get(SESSION_COOKIE))
    if record is None:
        return None, None, source
    session = record[0]
    return session.user_id, session.username, source


def address_of(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def record_entry(request: Request, **entry: Any) -> None:
    """Write one entry; a failure is logged and never fails the request."""

    context = getattr(request.app.state, "entropy_context", None)
    manager = getattr(context, "database_manager", None)
    if manager is None:
        return
    try:
        from lib.audit.store import AuditStore

        store = AuditStore(manager.connection)
        store.record(
            address=address_of(request),
            user_agent=request.headers.get("user-agent"),
            **entry,
        )
    except Exception as error:  # noqa: BLE001 - auditing must not break the operation
        LOGGER.warning("Unable to write the audit entry: %s", error)
        return
    _purge_now_and_then(request, store)


def _purge_now_and_then(request: Request, store: Any) -> None:
    global _last_purge
    if time.monotonic() - _last_purge < PURGE_EVERY:
        return
    _last_purge = time.monotonic()
    try:
        from core.web.routes.audit import purge_expired

        purge_expired(request, store)
    except Exception as error:  # noqa: BLE001 - housekeeping retries on a later entry
        LOGGER.warning("Unable to remove expired audit entries: %s", error)


async def audit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    method = request.method.upper()
    path = request.url.path
    if not should_audit(method, path):
        return await call_next(request)

    started = time.monotonic()
    try:
        user_id, username, source = await run_in_threadpool(_who, request)
    except Exception as error:  # noqa: BLE001 - an unknown caller is still audited
        LOGGER.warning("Unable to identify the caller for the audit log: %s", error)
        user_id, username, source = None, None, "web"
    raw = await request.body() if method in MUTATING else b""

    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        template = getattr(route, "path", None) or path
        category, action = describe(method, template)
        params: Dict[str, Any] = dict(request.scope.get("path_params") or {})
        from core.web.projects import PROJECT_HEADER

        details: Dict[str, Any] = {"route": f"{method} {template}"}
        if request.url.query:
            details["query"] = request.url.query[:500]
        entry = dict(
            category=category,
            action=action,
            outcome="success" if status < 400 else "denied" if status in (401, 403) else "failure",
            username=username,
            user_id=user_id,
            target=target(params, _body_name(raw, request.headers.get("content-type", ""))),
            source=source,
            method=method,
            path=path,
            status=status,
            project=request.headers.get(PROJECT_HEADER) or request.query_params.get("project"),
            duration_ms=int((time.monotonic() - started) * 1000),
            details=details,
        )
        await run_in_threadpool(lambda: record_entry(request, **entry))
