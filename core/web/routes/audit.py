"""Audit log API: search, export and retention (Administration -> Audit)."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import require
from core.web.routes.auth import _current_session, verify_csrf
from lib.audit.store import SORTS, AuditStore
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/audit", tags=["audit"])
SessionRecord = Tuple[Session, str, User]
EXPORT_LIMIT = 100000


class RetentionUpdate(BaseModel):
    retention_days: int = Field(ge=1, le=3650)


def _store(request: Request) -> AuditStore:
    return AuditStore(request.app.state.entropy_context.database_manager.connection)


def _reader(request: Request, record: SessionRecord) -> User:
    _, _, user = record
    require(request, user, "audit.read")
    return user


def _filters(
    search: str, user: str, category: str, outcome: str, project: str, since: str, until: str
) -> Dict[str, str]:
    return {
        "search": search,
        "username": user,
        "category": category,
        "outcome": outcome,
        "project": project,
        "since": since,
        "until": until,
    }


def retention_days(request: Request) -> int:
    from lib.audit.store import DEFAULT_RETENTION_DAYS
    from lib.system.settings import settings_for

    try:
        return int(
            settings_for(request.app.state.entropy_context).values("audit")["retention_days"]
        )
    except (KeyError, TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS


@router.get("")
def list_audit(
    request: Request,
    response: Response,
    search: str = Query("", max_length=200),
    user: str = Query("", max_length=150),
    category: str = Query("", max_length=60),
    outcome: str = Query("", max_length=10),
    project: str = Query("", max_length=100),
    since: str = Query("", max_length=40),
    until: str = Query("", max_length=40),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: str = Query("time", max_length=20),
    order: Literal["asc", "desc"] = Query("desc"),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Audit entries, newest first by default, with the values to filter by."""

    _reader(request, record)
    store = _store(request)
    items, total = store.search(
        limit=limit,
        offset=offset,
        sort=sort if sort in SORTS else "time",
        order=order,
        **_filters(search, user, category, outcome, project, since, until),
    )
    response.headers["Cache-Control"] = "no-store"
    _, _, current = record
    assert current.id is not None
    can_manage = request.app.state.entropy_context.authorization.has_permission(
        current.id, "system.settings"
    )
    return {
        "items": items,
        "total": total,
        "facets": store.facets(),
        "retention_days": retention_days(request),
        "can_manage": bool(can_manage),
    }


@router.get("/export.csv")
def export_audit(
    request: Request,
    search: str = Query("", max_length=200),
    user: str = Query("", max_length=150),
    category: str = Query("", max_length=60),
    outcome: str = Query("", max_length=10),
    project: str = Query("", max_length=100),
    since: str = Query("", max_length=40),
    until: str = Query("", max_length=40),
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """The matching entries as CSV (newest first, at most 100,000)."""

    _reader(request, record)
    rows = _store(request).export(
        limit=EXPORT_LIMIT, **_filters(search, user, category, outcome, project, since, until)
    )
    columns = [
        "created_at",
        "username",
        "source",
        "address",
        "category",
        "action",
        "target",
        "outcome",
        "status",
        "method",
        "path",
        "project",
        "duration_ms",
        "user_agent",
        "details",
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(
            [
                json.dumps(row.get(column)) if column == "details" else row.get(column)
                for column in columns
            ]
        )
    return Response(
        "﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="entropy-audit.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.put("/retention", dependencies=[Depends(verify_csrf)])
def set_retention(
    payload: RetentionUpdate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """How long entries are kept (system.settings); older ones are removed now."""

    from lib.system.settings import SettingsError, settings_for

    _, _, user = record
    require(request, user, "system.settings")
    try:
        settings_for(request.app.state.entropy_context).update(
            "audit", {"retention_days": payload.retention_days}
        )
    except SettingsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    removed = _store(request).purge(payload.retention_days)
    return {"retention_days": payload.retention_days, "removed": removed}


def purge_expired(request: Request, store: Optional[AuditStore] = None) -> int:
    """Housekeeping: remove entries older than the retention."""

    return (store or _store(request)).purge(retention_days(request))
