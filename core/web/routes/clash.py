"""
Clash: compare one schema in two Oracle databases.

Credentials come from the project's Vault, as JSON with username and password (the form
sqlplus.generic takes), and need vault.read there: whoever may compare could already sign
in to those databases with those credentials. A vault value never goes back to the browser.

A comparison runs in the background (lib/tools/clash/jobs.py): starting one answers at once,
and only the person who started it can follow it, in the project it started in.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import current_project
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.session import Session
from lib.models.users import User
from lib.tools.clash.database import (
    DatabaseCompareError,
    Endpoint,
    check_options,
    compare_rows,
    parse_names,
)
from lib.tools.clash.jobs import JOBS, CompareBusy, CompareJob
from lib.tools.clash.report import render_report
from lib.vault.exceptions import VaultError

router = APIRouter(prefix="/api/clash/database", tags=["clash"])

SessionRecord = tuple[str, Session, User]


class SideRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=1521, ge=1, le=65535)
    sid: str = Field(min_length=1, max_length=128)
    schema_name: str = Field(min_length=1, max_length=128)
    namespace: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=1, max_length=255)


class VaultReference(BaseModel):
    namespace: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=1, max_length=255)


class CompareRequest(BaseModel):
    left: SideRequest
    right: SideRequest
    ddl: bool = True
    data: bool = True
    name_filter: Optional[str] = Field(default=None, max_length=128)
    # Tables to compare by name (either list, or the name filter, is enough to be compared).
    tables: List[str] = Field(default_factory=list, max_length=1000)
    tables_vault: Optional[VaultReference] = None
    object_types: Optional[List[str]] = Field(default=None, max_length=32)


class ConfirmRequest(BaseModel):
    skip_large: bool = False


class RowsRequest(BaseModel):
    left: SideRequest
    right: SideRequest
    table: str = Field(min_length=1, max_length=128)


def _endpoint(request: Request, user: User, project_id: int, side: SideRequest) -> Endpoint:
    """The side's connection, with its credentials read from this project's Vault."""

    reference = f"{side.namespace}/{side.key}"
    value = _vault_value(request, user, project_id, side.namespace, side.key)

    try:
        credentials = json.loads(value) if isinstance(value, str) else value
    except ValueError:
        credentials = None

    if not isinstance(credentials, dict) or not all(
        isinstance(credentials.get(name), str) for name in ("username", "password")
    ):
        raise HTTPException(
            status_code=422,
            detail=f"'{reference}' must be JSON with 'username' and 'password'.",
        )

    return Endpoint(
        host=side.host,
        port=side.port,
        sid=side.sid,
        username=credentials["username"],
        password=credentials["password"],
        schema=side.schema_name,
    )


def _vault_value(request: Request, user: User, project_id: int, namespace: str, key: str) -> Any:
    """An entry of this project's Vault, as the person may read it."""

    from core.web.routes.vault import _require, _vault_components

    _require(request, user, "vault.read", project_id)
    vault_manager, namespace_manager = _vault_components(request)
    try:
        found = namespace_manager.get(namespace, project_id)
        return vault_manager.get(found.id, key)
    except VaultError:
        raise HTTPException(
            status_code=404, detail=f"'{namespace}/{key}' is not in this project's Vault."
        ) from None


def _table_names(request: Request, user: User, project_id: int, payload: Any) -> List[str]:
    """The tables named on the page and in the chosen Vault entry, each once."""

    names = parse_names(payload.tables)
    if payload.tables_vault is not None:
        reference = payload.tables_vault
        value = _vault_value(request, user, project_id, reference.namespace, reference.key)
        try:
            listed = parse_names(value)
        except DatabaseCompareError as exc:
            raise DatabaseCompareError(f"'{reference.namespace}/{reference.key}': {exc}") from None
        names += [name for name in listed if name not in names]
        if not listed:
            raise DatabaseCompareError(f"'{reference.namespace}/{reference.key}' lists no tables.")
    return names


def _project_id(request: Request, user: User) -> int:
    return int(current_project(request, user)["id"])


def _job(request: Request, user: User, job_id: str) -> CompareJob:
    """This person's comparison in the current project; anyone else's does not exist."""

    job = JOBS.current(int(user.id or 0), _project_id(request, user))
    if job is None or job.id != job_id:
        raise HTTPException(status_code=404, detail="That comparison is no longer available.")
    return job


def _notifier(request: Request) -> Any:
    from lib.database.repositories.notifications import notify_user

    context = request.app.state.entropy_context

    def notify(user_id: int, title: str, message: str, level: str, source: str) -> None:
        notify_user(context, user_id, title, message, level, source)

    return notify


@router.post("/compare", status_code=202, dependencies=[Depends(verify_csrf)])
def start_compare(
    payload: CompareRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """
    Start comparing DDL and table data in the background: counts and hashes, then the rows
    of the tables whose rows differ.
    """

    _, _, user = record
    project_id = _project_id(request, user)

    if not payload.ddl and not payload.data:
        raise HTTPException(status_code=422, detail="Choose DDL, data or both.")

    try:
        names = _table_names(request, user, project_id, payload)
        check_options(
            include_data=payload.data,
            name_filter=payload.name_filter or None,
            object_types=payload.object_types,
            names=names,
        )
        job = JOBS.start(
            user_id=int(user.id or 0),
            project_id=project_id,
            left=_endpoint(request, user, project_id, payload.left),
            right=_endpoint(request, user, project_id, payload.right),
            sides={"left": payload.left.model_dump(), "right": payload.right.model_dump()},
            include_ddl=payload.ddl,
            include_data=payload.data,
            name_filter=payload.name_filter or None,
            object_types=payload.object_types,
            notify=_notifier(request),
            names=names,
            names_source={
                "typed": parse_names(payload.tables),
                "vault": payload.tables_vault.model_dump() if payload.tables_vault else None,
            },
        )
    except CompareBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except DatabaseCompareError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    return job.snapshot()


@router.get("/compare/current")
def current_compare(
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """This person's latest comparison in this project, so a page can pick it up again."""

    _, _, user = record
    job = JOBS.current(int(user.id or 0), _project_id(request, user))
    return {"job": job.snapshot() if job else None}


@router.get("/compare/{job_id}")
def compare_status(
    job_id: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """How far a comparison has come."""

    return _job(request, record[2], job_id).snapshot()


@router.post("/compare/{job_id}/confirm", dependencies=[Depends(verify_csrf)])
def confirm_compare(
    job_id: str,
    payload: ConfirmRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """Go ahead with a comparison that waits for consent, with or without its large tables."""

    job = _job(request, record[2], job_id)
    try:
        job.confirm(payload.skip_large)
    except DatabaseCompareError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return job.snapshot()


@router.post("/compare/{job_id}/stop", dependencies=[Depends(verify_csrf)])
def stop_compare(
    job_id: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """Stop a comparison: at once if it is waiting, otherwise after the current batch."""

    job = _job(request, record[2], job_id)
    job.stop()
    return job.snapshot()


def _finished(request: Request, user: User, job_id: str) -> CompareJob:
    job = _job(request, user, job_id)
    if job.result is None:
        raise HTTPException(status_code=409, detail="This comparison has no result yet.")
    return job


@router.get("/compare/{job_id}/result")
def compare_result(
    job_id: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """
    The result of a comparison ("complete": True), or while it runs, what is compared so
    far ("complete": False): objects and tables appear as soon as each batch is done.
    """

    job = _job(request, record[2], job_id)
    if job.result is not None:
        return {**job.result, "complete": True}
    partial = job.partial()
    if partial is None:
        raise HTTPException(status_code=409, detail="This comparison has no result yet.")
    return partial


@router.get("/compare/{job_id}/report")
def compare_report(
    job_id: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Response:
    """The result as a self-contained HTML file."""

    job = _finished(request, record[2], job_id)
    assert job.result is not None  # nosec B101 - _finished checked it
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"database-compare-{job.left_label}-{job.right_label}")
    return Response(
        content=render_report(
            job.result,
            name_filter=job.name_filter,
            object_types=job.object_types,
            tables=job.names,
            tables_vault=job.names_source.get("vault"),
            sides=job.sides,
        ),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}.html"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/rows", dependencies=[Depends(verify_csrf)])
def compare_table_rows(
    payload: RowsRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """The rows that differ in one table."""

    _, _, user = record
    project_id = _project_id(request, user)

    try:
        return compare_rows(
            _endpoint(request, user, project_id, payload.left),
            _endpoint(request, user, project_id, payload.right),
            payload.table,
        )
    except DatabaseCompareError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
