"""
EagleAPI (Tools gallery): collections, vault-backed environments and sending.

Everything is scoped to the current project (`X-Entropy-Project`):
- collections need workflows.read to view and workflows.write to change;
- environment values live in the project's vault namespace
  `eagleapi-<project key>`, created on the first value someone adds;
- sending needs workflows.execute. References to the vault resolve only
  namespaces of the current project the user may read;
- a collection (top-level item) can be restricted to some of the project's
  members (see lib.tools.eagleapi.access); others do not see it at all;
- each person's sent requests are kept in their own history.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field

from core.web.projects import authorization, current_project, projects, require
from core.web.routes.auth import _current_session, verify_csrf
from lib.models.authorization import VaultAccess, VaultVisibility
from lib.models.session import Session
from lib.models.users import User
from lib.models.vault import VaultValueType
from lib.tools.eagleapi import formats, namespace_name
from lib.tools.eagleapi.access import EagleAccess, EagleAccessError, Viewer
from lib.tools.eagleapi.client import EagleRequestError, execute
from lib.tools.eagleapi.history import EagleHistory, har
from lib.tools.eagleapi.references import (
    ENVIRONMENT_NAME,
    EagleReferenceError,
    Resolver,
    VaultValue,
    environments,
)
from lib.tools.eagleapi.store import (
    EagleItemNotFound,
    EagleStore,
    EagleStoreError,
    effective_tls,
    normalize_request,
)
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
    # The saved request this was sent from, for the history.
    item_id: Optional[int] = None
    record_history: bool = True


class AccessEntry(BaseModel):
    kind: str = Field(pattern="^(user|group)$")
    name: str = Field(min_length=1, max_length=255)
    level: str = Field(default="read", pattern="^(read|write)$")


class AccessWrite(BaseModel):
    restricted: bool
    entries: List[AccessEntry] = Field(default_factory=list, max_length=500)


class ExportRequest(BaseModel):
    ids: List[int] = Field(default_factory=list, max_length=1000)
    format: str = Field(default="eagleapi", pattern="^(eagleapi|postman|soapui)$")
    preserve: bool = True


class HistorySelection(BaseModel):
    ids: Optional[List[int]] = Field(default=None, max_length=1000)
    format: str = Field(default="json", pattern="^(json|har)$")


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
# Collection access
# ---------------------------------------------------------------------

LEVEL_RANK = {"read": 1, "write": 2, "manage": 3}


def _access_store(request: Request) -> EagleAccess:
    return EagleAccess(_context(request).database_manager.connection)


def _viewer(request: Request, user: User) -> Viewer:
    assert user.id is not None
    connection = _context(request).database_manager.connection
    groups = [
        int(row["group_id"])
        for row in connection.fetchall(
            "SELECT group_id FROM user_groups WHERE user_id = ?", (user.id,)
        )
    ]
    admin = authorization(request).has_permission(user.id, "projects.manage")
    return Viewer(user.id, user.username, groups, admin)


class _Scope:
    """What one person sees of a project's collections."""

    def __init__(self, request: Request, user: User, project: Dict[str, Any]) -> None:
        self.project = project
        self.store = _store(request)
        self.access = _access_store(request)
        self.viewer = _viewer(request, user)
        self.roots = self.store.roots(project["id"])
        self.restricted = self.access.restricted(project["id"])
        self._levels: Dict[int, Optional[str]] = {}

    def level(self, item_id: int) -> Optional[str]:
        root = self.roots.get(item_id)
        if root is None:
            return None
        if root["id"] not in self._levels:
            self._levels[root["id"]] = self.access.level(self.viewer, root, self.restricted)
        return self._levels[root["id"]]

    def require(self, item_id: int, needed: str) -> None:
        level = self.level(item_id)
        if level is None:
            # Hidden collections are not acknowledged.
            raise HTTPException(
                status_code=404, detail=f"Item {item_id} not found in this project."
            )
        if LEVEL_RANK[level] < LEVEL_RANK[needed]:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Only the collection's owner can change who may use it."
                    if needed == "manage"
                    else "You have read-only access to this collection."
                ),
            )

    def visible(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        shown = []
        for item in items:
            level = self.level(item["id"])
            if level is None:
                continue
            item = {**item, "access": level}
            if item["parent_id"] is None:
                item["restricted"] = item["id"] in self.restricted
            shown.append(item)
        return shown


def _members(request: Request, project: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """The project's member people (directly or through groups) and groups."""

    connection = _context(request).database_manager.connection
    users: Dict[str, Any] = {}
    groups: Dict[str, Any] = {}
    for member in projects(request).members(project["id"]):
        if member["kind"] == "group":
            groups[member["name"]] = {"name": member["name"]}
            for row in connection.fetchall(
                "SELECT u.username, u.full_name FROM users u"
                " JOIN user_groups ug ON ug.user_id = u.id"
                " JOIN groups g ON g.id = ug.group_id WHERE g.name = ?",
                (member["name"],),
            ):
                users.setdefault(
                    row["username"], {"name": row["username"], "full_name": row["full_name"]}
                )
        else:
            users[member["name"]] = {"name": member["name"], "full_name": member["full_name"]}
    return users, groups


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
    scope = _Scope(request, record[2], project)
    return {"items": scope.visible(scope.store.list(project["id"]))}


@router.get("/items/{item_id}")
def get_item(
    item_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    project = _scope(request, record[2], READ)
    response.headers["Cache-Control"] = "no-store"
    scope = _Scope(request, record[2], project)
    scope.require(item_id, "read")
    try:
        return {"item": scope.visible([scope.store.get(project["id"], item_id)])[0]}
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
    if payload.parent_id is not None:
        _Scope(request, user, project).require(payload.parent_id, "write")
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
    _Scope(request, record[2], project).require(item_id, "write")
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
    scope = _Scope(request, record[2], project)
    scope.require(item_id, "write")
    if payload.parent_id is not None:
        scope.require(payload.parent_id, "write")
        # A restricted collection that goes into a folder takes that folder's access.
        if item_id in scope.restricted:
            scope.require(item_id, "manage")
    try:
        item = _store(request).move(
            project["id"], item_id, parent_id=payload.parent_id, position=payload.position
        )
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None
    if payload.parent_id is not None and item_id in scope.restricted:
        scope.access.forget([item_id])
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
    scope = _Scope(request, user, project)
    scope.require(item_id, "write")
    try:
        item = _store(request).duplicate(project["id"], item_id, user=user.username)
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None
    if item_id in scope.restricted:
        # A copy of a restricted collection is restricted to the same people.
        _copy_access(request, scope, item_id, item["id"], user)
    return {"item": item}


@router.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    project = _scope(request, record[2], WRITE)
    scope = _Scope(request, record[2], project)
    scope.require(item_id, "write")
    if item_id in scope.restricted:
        scope.require(item_id, "manage")
    try:
        deleted = _store(request).delete(project["id"], item_id)
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None
    scope.access.forget([item_id])
    return {"deleted": deleted}


def _copy_access(request: Request, scope: _Scope, source: int, target: int, user: User) -> None:
    users, groups = _members(request, scope.project)
    scope.access.set(
        scope.project["id"],
        target,
        restricted=True,
        entries=scope.access.entries(source),
        allowed_users=set(users),
        allowed_groups=set(groups),
        updated_by=user.username,
    )


@router.get("/items/{item_id}/access")
def get_access(
    item_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Who may see a collection, and the project members who can be added."""

    user = record[2]
    project = _scope(request, user, READ)
    scope = _Scope(request, user, project)
    scope.require(item_id, "read")
    root = scope.roots[item_id]
    if root["id"] != item_id:
        raise HTTPException(
            status_code=400, detail="Access is set on collections (top-level items)."
        )
    response.headers["Cache-Control"] = "no-store"
    users, groups = _members(request, project)
    return {
        "restricted": item_id in scope.restricted,
        "owner": root["created_by"],
        "entries": scope.access.entries(item_id),
        "can_manage": scope.viewer.admin or root["created_by"] == user.username,
        "candidates": {
            "users": sorted(users.values(), key=lambda entry: entry["name"]),
            "groups": sorted(groups.values(), key=lambda entry: entry["name"]),
        },
    }


@router.put("/items/{item_id}/access")
def put_access(
    item_id: int,
    payload: AccessWrite,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """Restrict a collection to some project members, or open it to all of them."""

    user = record[2]
    project = _scope(request, user, WRITE)
    scope = _Scope(request, user, project)
    scope.require(item_id, "read")
    root = scope.roots[item_id]
    if root["id"] != item_id:
        raise HTTPException(
            status_code=400, detail="Access is set on collections (top-level items)."
        )
    owner = root["created_by"] == user.username
    if not (scope.viewer.admin or owner):
        raise HTTPException(
            status_code=403, detail="Only the collection's owner can change who may use it."
        )
    users, groups = _members(request, project)
    try:
        scope.access.set(
            project["id"],
            item_id,
            restricted=payload.restricted,
            entries=[entry.model_dump() for entry in payload.entries],
            allowed_users=set(users),
            allowed_groups=set(groups),
            updated_by=user.username,
        )
    except EagleAccessError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return get_access(item_id, request, Response(), record)


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
    item_name = None
    if payload.item_id is not None:
        scope = _Scope(request, user, project)
        scope.require(payload.item_id, "read")
        item_name = scope.store.get(project["id"], payload.item_id)["name"]
    try:
        data = normalize_request(payload.request)
        definition = json.loads(json.dumps(data))
        # Inherited or profile TLS comes from the project settings.
        tls, source = effective_tls(data, _store(request).settings(project["id"]))
        data["tls"] = {**tls, "mode": "custom", "profile": ""}
        resolver = Resolver(_fetcher(request, user, project["id"]), payload.environment)
        result = execute(
            data,
            resolver,
            namespace_name(project["key"]),
            poll_url=payload.poll_url,
        )
    except (EagleRequestError, EagleReferenceError, EagleStoreError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    result = {**result, "tls_source": source}
    if payload.record_history:
        assert user.id is not None
        result["history_id"] = _history(request).add(
            project["id"],
            user.id,
            definition=definition,
            result=result,
            item_id=payload.item_id,
            item_name=item_name,
            environment=payload.environment,
            poll=bool(payload.poll_url),
        )
    return result


# ---------------------------------------------------------------------
# Project settings (TLS profiles)
# ---------------------------------------------------------------------


@router.get("/settings")
def get_settings(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """The project's TLS profiles and default profile (vault references, no secrets)."""

    project = _scope(request, record[2], READ)
    response.headers["Cache-Control"] = "no-store"
    return _store(request).settings(project["id"])


@router.put("/settings")
def put_settings(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """Replace the project's settings; a profile requests still use cannot go."""

    user = record[2]
    project = _scope(request, user, WRITE)
    store = _store(request)
    current = store.settings(project["id"])
    wanted = payload.get("tls_profiles") if isinstance(payload.get("tls_profiles"), list) else []
    kept = {str(item.get("id")) for item in wanted if isinstance(item, dict)}
    for profile in current["tls_profiles"]:
        if profile["id"] not in kept:
            users = store.profile_users(project["id"], profile["id"])
            if users:
                visible = {
                    item["name"]
                    for item in _Scope(request, user, project).visible(store.list(project["id"]))
                }
                hidden = len([name for name in users if name not in visible])
                users = [name for name in users if name in visible] + (
                    [f"{hidden} request(s) you cannot see"] if hidden else []
                )
                raise HTTPException(
                    status_code=409,
                    detail=f"TLS profile '{profile['name']}' is used by "
                    + ", ".join(users[:5])
                    + (f" and {len(users) - 5} more" if len(users) > 5 else "")
                    + ". Change those requests first.",
                )
    try:
        return store.save_settings(project["id"], payload, user.username)
    except EagleStoreError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


# ---------------------------------------------------------------------
# History (each person's own)
# ---------------------------------------------------------------------


def _history(request: Request) -> EagleHistory:
    return EagleHistory(_context(request).database_manager.connection)


@router.get("/history")
def list_history(
    request: Request,
    response: Response,
    limit: int = 100,
    offset: int = 0,
    q: str = "",
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    user = record[2]
    project = _scope(request, user, READ)
    assert user.id is not None
    response.headers["Cache-Control"] = "no-store"
    return _history(request).list(
        project["id"],
        user.id,
        limit=max(1, min(limit, 500)),
        offset=max(0, offset),
        query=q.strip()[:200],
    )


@router.get("/history/{entry_id}")
def get_history(
    entry_id: int,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    user = record[2]
    project = _scope(request, user, READ)
    assert user.id is not None
    entry = _history(request).get(project["id"], user.id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="History entry not found.")
    response.headers["Cache-Control"] = "no-store"
    return {"entry": entry}


@router.post("/history/purge")
def purge_history(
    payload: HistorySelection,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """Delete your history in this project: everything, or the chosen entries."""

    user = record[2]
    project = _scope(request, user, READ)
    assert user.id is not None
    return {"deleted": _history(request).purge(project["id"], user.id, payload.ids)}


@router.post("/history/export")
def export_history(
    payload: HistorySelection,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Response:
    """Your history with the responses, as EagleAPI JSON or HAR."""

    from core.version import VERSION

    user = record[2]
    project = _scope(request, user, READ)
    assert user.id is not None
    entries = _history(request).entries(project["id"], user.id, payload.ids)
    if payload.format == "har":
        document: Dict[str, Any] = har(entries, VERSION)
        filename = f"eagleapi-history-{project['key']}.har"
    else:
        document = {
            "format": "entropy-eagleapi-history",
            "version": 1,
            "project": project["key"],
            "exported_by": user.username,
            "entries": entries,
        }
        filename = f"eagleapi-history-{project['key']}.json"
    return Response(
        json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------
# Export and import
# ---------------------------------------------------------------------


@router.post("/export")
def export_collections(
    payload: ExportRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Response:
    """Chosen collections (or all you can see) as EagleAPI, Postman or SoapUI."""

    user = record[2]
    project = _scope(request, user, READ)
    scope = _Scope(request, user, project)
    items = scope.visible(scope.store.list(project["id"]))
    ids = payload.ids or [item["id"] for item in items if item["parent_id"] is None]
    for item_id in ids:
        scope.require(item_id, "read")
    # A folder and something inside it: export the folder once.
    chosen: Set[int] = set(ids)
    parents = {item["id"]: item["parent_id"] for item in items}

    def inside_chosen(item_id: int) -> bool:
        parent = parents.get(item_id)
        while parent is not None:
            if parent in chosen:
                return True
            parent = parents.get(parent)
        return False

    ids = [item_id for item_id in ids if not inside_chosen(item_id)]
    if not ids:
        raise HTTPException(status_code=400, detail="There is nothing to export.")
    nodes = scope.store.tree(project["id"], ids)
    name = nodes[0]["name"] if len(nodes) == 1 else f"{project['name']} collections"
    content, media_type, extension = formats.export(
        payload.format,
        nodes,
        name=name,
        preserve=payload.preserve,
        settings=scope.store.settings(project["id"]) if payload.preserve else None,
        project=project["key"],
        exported_by=user.username,
    )
    safe = (
        "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in name).strip("-") or "eagleapi"
    )
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe}.{extension}"'},
    )


@router.post("/import")
async def import_collections(
    request: Request,
    file: UploadFile = File(...),
    parent_id: Optional[int] = Form(None),
    preserve: bool = Form(True),
    preview: bool = Form(False),
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Dict[str, Any]:
    """
    Read an EagleAPI, Postman, Insomnia or SoapUI export. With `preview`,
    only say what is in it; otherwise add its collections (in `parent_id`,
    or at the top level).
    """

    user = record[2]
    project = _scope(request, user, WRITE)
    scope = _Scope(request, user, project)
    if parent_id is not None:
        scope.require(parent_id, "write")
    raw = await file.read(formats.MAX_IMPORT_BYTES + 1)
    try:
        parsed = formats.read(raw, namespace_name(project["key"]), preserve)
    except formats.EagleFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    summary = {
        "format": parsed["format"],
        "name": parsed["name"],
        "collections": [node["name"] for node in parsed["collections"]],
        "folders": parsed["folders"],
        "requests": parsed["requests"],
        "warnings": parsed["warnings"],
        "tls_profiles": len((parsed["settings"] or {}).get("tls_profiles") or []),
    }
    if preview:
        return summary

    remap = None
    added_profiles: List[str] = []
    if parsed["settings"]:
        remap, added_profiles = _merge_profiles(request, scope, parsed["settings"], user)
    try:
        created = scope.store.add_tree(
            project["id"], parent_id, parsed["collections"], user.username, remap
        )
    except (EagleItemNotFound, EagleStoreError) as exc:
        raise _store_error(exc) from None
    return {**summary, "created": created, "added_profiles": added_profiles}


def _merge_profiles(
    request: Request, scope: _Scope, incoming: Dict[str, Any], user: User
) -> Tuple[Any, List[str]]:
    """
    Add the file's TLS profiles the project lacks (by name); returns a
    function that points requests at the project's profile ids.
    """

    store = scope.store
    project_id = scope.project["id"]
    current = store.settings(project_id)
    by_name = {profile["name"].lower(): profile for profile in current["tls_profiles"]}
    ids: Dict[str, str] = {}
    added = []
    for profile in incoming.get("tls_profiles") or []:
        existing = by_name.get(profile["name"].lower())
        if existing is not None:
            ids[profile["id"]] = existing["id"]
            continue
        new_id = "p" + uuid.uuid4().hex[:12]
        ids[profile["id"]] = new_id
        current["tls_profiles"].append({**profile, "id": new_id})
        by_name[profile["name"].lower()] = current["tls_profiles"][-1]
        added.append(profile["name"])
    if not current["default_tls"] and incoming.get("default_tls") in ids:
        current["default_tls"] = ids[incoming["default_tls"]]
    if added or current["default_tls"] != store.settings(project_id)["default_tls"]:
        store.save_settings(project_id, current, user.username)

    def remap(data: Dict[str, Any]) -> Dict[str, Any]:
        tls = dict(data.get("tls") or {})
        if tls.get("mode") == "profile":
            if tls.get("profile") in ids:
                tls["profile"] = ids[tls["profile"]]
            else:
                tls["mode"], tls["profile"] = "inherit", ""
        return {**data, "tls": tls}

    return remap, added
