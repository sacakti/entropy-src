"""
Clash: compare one schema in two Oracle databases.

Credentials come from the project's Vault, as JSON with username and password (the form
sqlplus.generic takes), and need vault.read there: whoever may compare could already sign
in to those databases with those credentials. A vault value never goes back to the browser.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.web.projects import current_project
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.session import Session
from lib.models.users import User
from lib.tools.clash.database import (
    DatabaseCompareError,
    Endpoint,
    compare,
    compare_rows,
)
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


class CompareRequest(BaseModel):
    left: SideRequest
    right: SideRequest
    ddl: bool = True
    data: bool = True
    name_filter: Optional[str] = Field(default=None, max_length=128)


class RowsRequest(BaseModel):
    left: SideRequest
    right: SideRequest
    table: str = Field(min_length=1, max_length=128)


def _endpoint(request: Request, user: User, project_id: int, side: SideRequest) -> Endpoint:
    """The side's connection, with its credentials read from this project's Vault."""

    from core.web.routes.vault import _require, _vault_components

    _require(request, user, "vault.read", project_id)
    vault_manager, namespace_manager = _vault_components(request)
    reference = f"{side.namespace}/{side.key}"

    try:
        namespace = namespace_manager.get(side.namespace, project_id)
        value = vault_manager.get(namespace.id, side.key)
    except VaultError:
        raise HTTPException(
            status_code=404, detail=f"'{reference}' is not in this project's Vault."
        ) from None

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


def _project_id(request: Request, user: User) -> int:
    return int(current_project(request, user)["id"])


@router.post("/compare", dependencies=[Depends(verify_csrf)])
def compare_schemas(
    payload: CompareRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """Compare DDL and table data: counts and hashes only, no rows."""

    _, _, user = record
    project_id = _project_id(request, user)

    if not payload.ddl and not payload.data:
        raise HTTPException(status_code=422, detail="Choose DDL, data or both.")

    try:
        return compare(
            _endpoint(request, user, project_id, payload.left),
            _endpoint(request, user, project_id, payload.right),
            include_ddl=payload.ddl,
            include_data=payload.data,
            name_filter=payload.name_filter or None,
        )
    except DatabaseCompareError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


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
