"""
EagleAPI (Tools gallery): collections, vault-backed environments and sending.

Everything is scoped to the current project (`X-Entropy-Project`):
- collections need workflows.read to view and workflows.write to change;
- environment values live in the project's vault namespace
  `eagleapi-<project key>`, created on the first value someone adds;
- sending needs workflows.execute. References to the vault resolve only
  namespaces of the current project the user may read.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from core.web.projects import current_project, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.authorization import VaultAccess, VaultVisibility
from lib.models.session import Session
from lib.models.users import User
from lib.models.vault import VaultValueType
from lib.tools.eagleapi import namespace_name
from lib.tools.eagleapi.client import EagleRequestError, execute
from lib.tools.eagleapi.references import (
    ENVIRONMENT_NAME,
    EagleReferenceError,
    Resolver,
    VaultValue,
    environments,
)
from lib.tools.eagleapi.store import EagleItemNotFound, EagleStore, EagleStoreError
from lib.vault.exceptions import VaultError, VaultNamespaceNotFoundError

router = APIRouter(prefix="/api/eagleapi", tags=["eagleapi"])

SessionRecord = Tuple[Session, str, User]

READ = "workflows.read"
WRITE = "workflows.write"
EXECUTE = "workflows.execute"


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------


class ItemCreate(BaseModel):
    kind: str = Field(pattern="^(folder|request)$")
    name: str = Field(min_length=1, max_length=120)
    parent_id: Optional[int] = None
    data: Optional[Dict[str, Any]] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    data: Optional[Dict[str, Any]] = None


class ItemMove(BaseModel):
    parent_id: Optional[int] = None
    position: Optional[int] = Field(default=None, ge=0)


class SendRequest(BaseModel):
    request: Dict[str, Any]
    environment: Optional[str] = Field(default=None, max_length=60)
    poll_url: Optional[str] = Field(default=None, max_length=8192)


class EntryWrite(BaseModel):
    value: str = Field(max_length=1024 * 1024)
    sensitive: bool = True


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    base_url: str = Field(min_length=1, max_length=4096)
    sensitive: bool = False


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _context(request: Request) -> Any:
    context = request.app.state.entropy_context
    if getattr(context, "database_manager", None) is None:
        raise HTTPException(status_code=503, detail="Database is unavailable.")
    return context


def _store(request: Request) -> EagleStore:
    return EagleStore(_context(request).database_manager.connection)


def _scope(request: Request, user: User, permission: str) -> Dict[str, Any]:
    project = current_project(request, user)
    require(request, user, permission, project["id"])
    return project


def _vault(request: Request) -> Tuple[Any, Any]:
    from core.web.routes.vault import _vault_components

    return _vault_components(request)


def _namespace(request: Request, project: Dict[str, Any]) -> Optional[Any]:
    """The project's EagleAPI namespace, or None while it does not exist."""

    from lib.vault.projects import namespace_project

    _, namespace_manager = _vault(request)
    try:
        namespace = namespace_manager.get(namespace_name(project["key"]))
    except VaultNamespaceNotFoundError:
        return None
    connection = _context(request).database_manager.connection
    if namespace_project(connection, namespace.id) != project["id"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"The vault namespace '{namespace.name}' belongs to another project; "
                "rename it there to use EagleAPI environments here."
            ),
        )
    return namespace


def _ensure_namespace(request: Request, user: User, project: Dict[str, Any]) -> Any:
    """The project's EagleAPI namespace, created (private, owned by the user) if missing."""

    from lib.vault.projects import set_namespace_project

    namespace = _namespace(request, project)
    if namespace is not None:
        return namespace
    _, namespace_manager = _vault(request)
    try:
        namespace = namespace_manager.create(
            name=namespace_name(project["key"]),
            owner_user_id=user.id,
            visibility=VaultVisibility.PRIVATE,
        )
    except VaultError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    connection = _context(request).database_manager.connection
    set_namespace_project(connection, namespace.id, project["id"])
    return namespace


def _access(request: Request, namespace: Any, user: User, needed: VaultAccess, perm: str) -> None:
    from core.web.routes.vault import _require_namespace_access

    _, namespace_manager = _vault(request)
    _require_namespace_access(request, namespace_manager, namespace, user, needed, perm)


def _fetcher(request: Request, user: User, project_id: int):
    """Reads a vault value for this user: current project only, with read access."""

    from core.web.routes.vault import _require_namespace_access
    from lib.vault.projects import namespace_project

    vault_manager, namespace_manager = _vault(request)
    connection = _context(request).database_manager.connection

    def fetch(namespace: str, key: str) -> VaultValue:
        reference = f"${{entv:{namespace}/{key}}}"
        try:
            record = namespace_manager.get(namespace)
        except VaultError:
            raise EagleReferenceError(
                f"{reference}: the namespace '{namespace}' does not exist."
            ) from None
        if record.id is None or namespace_project(connection, record.id) != project_id:
            raise EagleReferenceError(
                f"{reference}: the namespace '{namespace}' is not in this project."
            )
        try:
            _require_namespace_access(
                request, namespace_manager, record, user, VaultAccess.READ, "vault.read"
            )
        except HTTPException as exc:
            raise EagleReferenceError(f"{reference}: {exc.detail}") from None
        try:
            entry = vault_manager.get_entry(record.id, key)
            value = vault_manager.get(record.id, key)
        except VaultError:
            raise EagleReferenceError(f"{reference}: no such key in the vault.") from None
        return VaultValue(value=value, type=entry.type.value, sensitive=bool(entry.sensitive))

    return fetch


def _entry_view(vault_manager: Any, namespace_id: int, entry: Any) -> Dict[str, Any]:
    """An environment value for the browser: sensitive values are never sent."""

    view: Dict[str, Any] = {
        "key": entry.key,
        "type": entry.type.value,
        "sensitive": bool(entry.sensitive),
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }
    if entry.type is VaultValueType.FILE:
        from lib.vault.files import metadata

        view["file"] = metadata(vault_manager.get(namespace_id, entry.key))
    elif not entry.sensitive:
        value = vault_manager.get(namespace_id, entry.key)
        view["value"] = value if isinstance(value, str) else str(value)
    return view


def _check_key(key: str) -> str:
    key = key.strip()
    valid = all(ch.isascii() and (ch.isalnum() or ch == "_") for ch in key)
    if not key or len(key) > 255 or not valid:
        raise HTTPException(
            status_code=422,
            detail="Keys may contain only letters, numbers and underscore (_).",
        )
    return key


def _store_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EagleItemNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------


@router.get("/items")
def list_items(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    project = _scope(request, record[2], READ)
    response.headers["Cache-Control"] = "no-store"
    return {"items": _store(request).list(project["id"])}


@router.get("/items/{item_id}")
def get_item(
    item_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    project = _scope(request, record[2], READ)
    response.headers["Cache-Control"] = "no-store"
    try:
        return {"item": _store(request).get(project["id"], item_id)}
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None


@router.post("/items", status_code=201)
def create_item(
    payload: ItemCreate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    user = record[2]
    project = _scope(request, user, WRITE)
    try:
        item = _store(request).create(
            project["id"],
            kind=payload.kind,
            name=payload.name,
            parent_id=payload.parent_id,
            data=payload.data,
            user=user.username,
        )
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None
    return {"item": item}


@router.patch("/items/{item_id}")
def update_item(
    item_id: int,
    payload: ItemUpdate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    project = _scope(request, record[2], WRITE)
    try:
        item = _store(request).update(project["id"], item_id, name=payload.name, data=payload.data)
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None
    return {"item": item}


@router.post("/items/{item_id}/move")
def move_item(
    item_id: int,
    payload: ItemMove,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    project = _scope(request, record[2], WRITE)
    try:
        item = _store(request).move(
            project["id"], item_id, parent_id=payload.parent_id, position=payload.position
        )
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None
    return {"item": item}


@router.post("/items/{item_id}/duplicate", status_code=201)
def duplicate_item(
    item_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    user = record[2]
    project = _scope(request, user, WRITE)
    try:
        item = _store(request).duplicate(project["id"], item_id, user=user.username)
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None
    return {"item": item}


@router.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    project = _scope(request, record[2], WRITE)
    try:
        deleted = _store(request).delete(project["id"], item_id)
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None
    return {"deleted": deleted}


# ---------------------------------------------------------------------
# Environment (the project's EagleAPI vault namespace)
# ---------------------------------------------------------------------


@router.get("/environment")
def get_environment(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """The namespace's keys (sensitive values masked) and the environments."""

    user = record[2]
    project = _scope(request, user, READ)
    response.headers["Cache-Control"] = "no-store"
    name = namespace_name(project["key"])
    payload: Dict[str, Any] = {
        "namespace": name,
        "exists": False,
        "access": None,
        "entries": [],
        "environments": [],
    }
    namespace = _namespace(request, project)
    if namespace is None:
        return payload

    vault_manager, namespace_manager = _vault(request)
    access = namespace_manager.access_by_user_id(namespace, user.id)
    payload["exists"] = True
    payload["access"] = access.value if access is not None else None
    try:
        _access(request, namespace, user, VaultAccess.READ, "vault.read")
    except HTTPException as exc:
        payload["message"] = str(exc.detail)
        return payload
    entries = sorted(vault_manager.list(namespace.id), key=lambda entry: entry.key)
    payload["entries"] = [_entry_view(vault_manager, namespace.id, entry) for entry in entries]
    payload["environments"] = environments(entry.key for entry in entries)
    return payload


def _writable_namespace(request: Request, user: User, project: Dict[str, Any], key: str) -> Any:
    namespace = _ensure_namespace(request, user, project)
    vault_manager, _ = _vault(request)
    exists = vault_manager.exists(namespace.id, key)
    _access(request, namespace, user, VaultAccess.WRITE, "vault.modify" if exists else "vault.add")
    return namespace


def _put(
    request: Request, namespace: Any, key: str, value: Any, kind: VaultValueType, sensitive: bool
) -> Any:
    vault_manager, _ = _vault(request)
    store = vault_manager.update if vault_manager.exists(namespace.id, key) else vault_manager.add
    try:
        return store(
            namespace_id=namespace.id,
            key=key,
            value=value,
            value_type=kind,
            sensitive=sensitive,
        )
    except (VaultError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.put("/environment/entries/{key}")
def put_entry(
    key: str,
    payload: EntryWrite,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """Add or replace a text value (creating the project's namespace if needed)."""

    user = record[2]
    project = _scope(request, user, WRITE)
    key = _check_key(key)
    namespace = _writable_namespace(request, user, project, key)
    entry = _put(request, namespace, key, payload.value, VaultValueType.STRING, payload.sensitive)
    vault_manager, _ = _vault(request)
    return {"entry": _entry_view(vault_manager, namespace.id, entry)}


@router.post("/environment/files", status_code=201)
async def upload_entry_file(
    request: Request,
    key: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    sensitive: bool = Form(True),
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """Keep a file (certificate, key, PFX/P12, CA bundle) under `key`."""

    from lib.vault.files import MAX_FILE_BYTES, VaultFileError, make_value

    user = record[2]
    project = _scope(request, user, WRITE)
    key = _check_key(key)
    content = await file.read(MAX_FILE_BYTES + 1)
    try:
        value = make_value(file.filename or key, content, file.content_type)
    except VaultFileError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None
    namespace = _writable_namespace(request, user, project, key)
    entry = _put(request, namespace, key, value, VaultValueType.FILE, sensitive)
    vault_manager, _ = _vault(request)
    return {"entry": _entry_view(vault_manager, namespace.id, entry)}


@router.delete("/environment/entries/{key}")
def delete_entry(
    key: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    user = record[2]
    project = _scope(request, user, WRITE)
    namespace = _namespace(request, project)
    if namespace is None:
        raise HTTPException(status_code=404, detail="The project has no EagleAPI values yet.")
    _access(request, namespace, user, VaultAccess.WRITE, "vault.delete")
    vault_manager, _ = _vault(request)
    try:
        vault_manager.delete(namespace.id, key)
    except VaultError:
        raise HTTPException(status_code=404, detail=f"'{key}' does not exist.") from None
    return {"deleted": key}


@router.post("/environment/environments", status_code=201)
def create_environment(
    payload: EnvironmentCreate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """A new environment: its base URL kept as `<NAME>_URL`."""

    user = record[2]
    project = _scope(request, user, WRITE)
    name = payload.name.strip().upper()
    if not ENVIRONMENT_NAME.match(name):
        raise HTTPException(
            status_code=422,
            detail="Environment names use capital letters, digits and _ (e.g. SIT, UAT, PROD).",
        )
    base_url = payload.base_url.strip()
    if not base_url.lower().startswith(("http://", "https://")) and "${" not in base_url:
        raise HTTPException(
            status_code=422, detail="The base URL must start with http:// or https://."
        )
    key = f"{name}_URL"
    namespace = _writable_namespace(request, user, project, key)
    vault_manager, _ = _vault(request)
    if vault_manager.exists(namespace.id, key):
        raise HTTPException(status_code=409, detail=f"The environment {name} already exists.")
    entry = _put(request, namespace, key, base_url, VaultValueType.STRING, payload.sensitive)
    return {"environment": name, "entry": _entry_view(vault_manager, namespace.id, entry)}


# ---------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------


@router.post("/send")
def send_request(
    payload: SendRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """
    Send a request definition (saved or not) in the selected environment.
    With `poll_url`, send the request's poll instead (the browser drives the
    polling: one call per attempt).
    """

    user = record[2]
    project = _scope(request, user, EXECUTE)
    response.headers["Cache-Control"] = "no-store"
    try:
        resolver = Resolver(_fetcher(request, user, project["id"]), payload.environment)
        return execute(
            payload.request,
            resolver,
            namespace_name(project["key"]),
            poll_url=payload.poll_url,
        )
    except (EagleRequestError, EagleReferenceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
