"""
Vault namespace and secret management API.

Vault namespaces belong to a project. Every request works in the current
project (the UI's project switcher, `X-Entropy-Project`), and access comes
only from the caller's roles in that project (see lib.vault.access).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field

from core.web.routes.auth import _current_session, verify_csrf
from lib.models.session import Session
from lib.models.users import User
from lib.models.vault import VaultValueType
from lib.vault.exceptions import (
    VaultAccessDeniedError,
    VaultEntryExistsError,
    VaultEntryNotFoundError,
    VaultError,
    VaultNamespaceExistsError,
    VaultNamespaceNameError,
    VaultNamespaceNotFoundError,
    VaultValueError,
)

router = APIRouter(prefix="/api/vault", tags=["vault"])

SessionRecord = tuple[Session, str, User]


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------


class NamespaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class NamespaceUpdateRequest(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


class EntryCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    value: Any
    type: VaultValueType = VaultValueType.STRING
    sensitive: bool = True


class EntryUpdateRequest(BaseModel):
    value: Any
    type: VaultValueType = VaultValueType.STRING
    sensitive: bool = True


# ---------------------------------------------------------------------
# Dependencies and error handling
# ---------------------------------------------------------------------


def _vault_components(request: Request) -> tuple[Any, Any]:
    """Resolve the existing Vault and namespace managers."""
    context = request.app.state.entropy_context

    vault_manager = getattr(context, "vault_manager", None)
    namespace_manager = getattr(
        context,
        "vault_namespace_manager",
        None,
    )

    if vault_manager is None or namespace_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Vault is unavailable.",
        )

    return vault_manager, namespace_manager


def _raise_http_error(exc: Exception) -> None:
    """Translate known Vault exceptions to safe HTTP responses."""
    if isinstance(exc, VaultAccessDeniedError):
        raise HTTPException(
            status_code=403,
            detail="Vault access denied.",
        ) from exc

    if isinstance(
        exc,
        (
            VaultEntryNotFoundError,
            VaultNamespaceNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=404,
            detail="Vault resource not found.",
        ) from exc

    if isinstance(
        exc,
        (
            VaultEntryExistsError,
            VaultNamespaceExistsError,
            VaultNamespaceNameError,
            VaultValueError,
        ),
    ):
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if isinstance(exc, VaultError):
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    raise exc


# ---------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------


def _namespace_payload(
    namespace: Any,
) -> dict[str, Any]:
    return {
        "id": namespace.id,
        "name": namespace.name,
        "project_id": namespace.project_id,
        "owner_user_id": namespace.owner_user_id,
        "created_at": (namespace.created_at.isoformat() if namespace.created_at else None),
        "updated_at": (namespace.updated_at.isoformat() if namespace.updated_at else None),
    }


def _entry_metadata(entry: Any) -> dict[str, Any]:
    """Return metadata only; never serialize the stored value."""
    return {
        "id": entry.id,
        "key": entry.key,
        "type": entry.type.value,
        "sensitive": entry.sensitive,
        "created_at": (entry.created_at.isoformat() if entry.created_at else None),
        "updated_at": (entry.updated_at.isoformat() if entry.updated_at else None),
    }


def _entry_payload(vault_manager: Any, namespace_id: int, entry: Any) -> dict[str, Any]:
    """Metadata, plus a file's name, type and size (never its content)."""
    payload = _entry_metadata(entry)
    if entry.type is VaultValueType.FILE:
        from lib.vault.files import metadata

        payload["file"] = metadata(vault_manager.get(namespace_id, entry.key))
    return payload


# ---------------------------------------------------------------------
# Project roles
# ---------------------------------------------------------------------


# The caller's Vault abilities in a project, as the UI names them.
_PERMISSIONS = {
    "namespace_read": "vault.namespace.read",
    "reveal": "vault.read",
    "add": "vault.add",
    "modify": "vault.modify",
    "delete": "vault.delete",
    "namespace_create": "vault.namespace.create",
    "namespace_modify": "vault.namespace.modify",
    "namespace_delete": "vault.namespace.delete",
}


def _can(request: Request, user: User, permission: str, project_id: int) -> bool:
    from lib.vault.access import can

    return can(request.app.state.entropy_context.authorization, user.id, permission, project_id)


def _require(request: Request, user: User, permission: str, project_id: int) -> None:
    """403 unless the user holds the Vault permission in the project."""

    if not _can(request, user, permission, project_id):
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: this needs {permission} in this project.",
        )


def _permissions(request: Request, user: User, project_id: int) -> dict[str, bool]:
    return {
        name: _can(request, user, permission, project_id)
        for name, permission in _PERMISSIONS.items()
    }


def _project_id(request: Request) -> int:
    """The current project (the UI's project switcher)."""

    from core.web.projects import current_project

    record = _current_session(request)
    return current_project(request, record[2])["id"]


def _get_namespace(
    request: Request,
    namespace_manager: Any,
    namespace_name: str,
    project_id: Optional[int] = None,
) -> Any:
    """A namespace of the current (or given) project; others are 'not found' here."""
    try:
        return namespace_manager.get(
            namespace_name,
            project_id if project_id is not None else _project_id(request),
        )
    except VaultError as exc:
        _raise_http_error(exc)


# ---------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------


@router.get("/namespaces")
def list_namespaces(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """The current project's namespaces, and what the caller may do there."""
    _, _, user = record

    _, namespace_manager = _vault_components(request)

    project_id = _project_id(request)
    permissions = _permissions(request, user, project_id)

    try:
        namespaces = namespace_manager.list(project_id) if permissions["namespace_read"] else []
    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    return {
        "items": [_namespace_payload(namespace) for namespace in namespaces],
        "permissions": permissions,
    }


@router.post("/namespaces", status_code=201)
def create_namespace(
    payload: NamespaceCreateRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """Create a namespace in the current project."""
    _, _, user = record
    project_id = _project_id(request)
    _require(request, user, "vault.namespace.create", project_id)

    _, namespace_manager = _vault_components(request)

    try:
        namespace = namespace_manager.create(
            name=payload.name.strip(),
            project_id=project_id,
            owner_user_id=user.id,
        )
    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    return {"namespace": _namespace_payload(namespace)}


@router.patch("/namespaces/{namespace_name}")
def update_namespace(
    namespace_name: str,
    payload: NamespaceUpdateRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """Rename a namespace within its project."""
    _, _, user = record

    _, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            request,
            namespace_manager,
            namespace_name,
        )

        _require(request, user, "vault.namespace.modify", namespace.project_id)

        namespace = namespace_manager.modify(
            namespace,
            name=payload.name,
        )
    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    return {"namespace": _namespace_payload(namespace)}


@router.delete(
    "/namespaces/{namespace_name}",
    status_code=204,
)
def delete_namespace(
    namespace_name: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """Delete a namespace and its dependent entries."""
    _, _, user = record

    _, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            request,
            namespace_manager,
            namespace_name,
        )

        _require(request, user, "vault.namespace.delete", namespace.project_id)

        namespace_manager.delete(namespace)
    except VaultError as exc:
        _raise_http_error(exc)

    return Response(
        status_code=204,
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------
# Vault entries
# ---------------------------------------------------------------------


@router.get("/namespaces/{namespace_name}/entries")
def list_entries(
    namespace_name: str,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """List entry metadata without revealing secret values."""
    _, _, user = record

    vault_manager, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            request,
            namespace_manager,
            namespace_name,
        )

        _require(request, user, "vault.namespace.read", namespace.project_id)

        if namespace.id is None:
            raise HTTPException(
                status_code=404,
                detail="Vault namespace not found.",
            )

        entries = vault_manager.list(namespace.id)

    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    return {"items": [_entry_payload(vault_manager, namespace.id, entry) for entry in entries]}


@router.post(
    "/namespaces/{namespace_name}/entries",
    status_code=201,
)
def create_entry(
    namespace_name: str,
    payload: EntryCreateRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """Create an entry through the existing VaultManager."""
    _, _, user = record

    vault_manager, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            request,
            namespace_manager,
            namespace_name,
        )

        _require(request, user, "vault.add", namespace.project_id)

        if namespace.id is None:
            raise HTTPException(
                status_code=404,
                detail="Vault namespace not found.",
            )

        entry = vault_manager.add(
            namespace_id=namespace.id,
            key=payload.key,
            value=payload.value,
            value_type=payload.type,
            sensitive=payload.sensitive,
        )

    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    return {"entry": _entry_metadata(entry)}


@router.put(
    "/namespaces/{namespace_name}/entries/{key}",
)
def update_entry(
    namespace_name: str,
    key: str,
    payload: EntryUpdateRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """Update an existing entry."""
    _, _, user = record

    vault_manager, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            request,
            namespace_manager,
            namespace_name,
        )

        _require(request, user, "vault.modify", namespace.project_id)

        if namespace.id is None:
            raise HTTPException(
                status_code=404,
                detail="Vault namespace not found.",
            )

        entry = vault_manager.update(
            namespace_id=namespace.id,
            key=key,
            value=payload.value,
            value_type=payload.type,
            sensitive=payload.sensitive,
        )

    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    return {"entry": _entry_metadata(entry)}


@router.post(
    "/namespaces/{namespace_name}/entries/{key}/reveal",
)
def reveal_entry(
    namespace_name: str,
    key: str,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """Explicitly resolve an entry's value."""
    _, _, user = record

    vault_manager, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            request,
            namespace_manager,
            namespace_name,
        )

        _require(request, user, "vault.read", namespace.project_id)

        if namespace.id is None:
            raise HTTPException(
                status_code=404,
                detail="Vault namespace not found.",
            )

        entry = vault_manager.get_entry(
            namespace.id,
            key,
        )

        value = vault_manager.get(
            namespace.id,
            key,
        )

    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    if entry.type is VaultValueType.FILE:
        # Files are downloaded, not shown: the value is the file's details.
        from lib.vault.files import metadata

        value = metadata(value)

    return {
        "entry": {
            **_entry_payload(vault_manager, namespace.id, entry),
            "value": value,
        }
    }


@router.delete(
    "/namespaces/{namespace_name}/entries/{key}",
    status_code=204,
)
def delete_entry(
    namespace_name: str,
    key: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """Delete an entry."""
    _, _, user = record

    vault_manager, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            request,
            namespace_manager,
            namespace_name,
        )

        _require(request, user, "vault.delete", namespace.project_id)

        if namespace.id is None:
            raise HTTPException(
                status_code=404,
                detail="Vault namespace not found.",
            )

        vault_manager.delete(
            namespace_id=namespace.id,
            key=key,
        )

    except VaultError as exc:
        _raise_http_error(exc)

    return Response(
        status_code=204,
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------
# Export and import (passphrase-encrypted files)
# ---------------------------------------------------------------------


class VaultExportRequest(BaseModel):
    namespaces: list[str] = Field(min_length=1, max_length=500)
    passphrase: str = Field(min_length=1, max_length=1024)


def _readable_namespaces(
    request: Request, user: User, names: list[str], project_id: Optional[int] = None
) -> list[Any]:
    """The namespaces, each checked for read access (reveal-level)."""

    _, namespace_manager = _vault_components(request)
    found = []
    for name in dict.fromkeys(names):
        try:
            namespace = _get_namespace(request, namespace_manager, name, project_id)
            _require(request, user, "vault.read", namespace.project_id)
        except VaultError as exc:
            _raise_http_error(exc)
        found.append(namespace)
    return found


def _may_write(request: Request, user: User):
    def check(namespace: Any) -> bool:
        return _can(request, user, "vault.add", namespace.project_id)

    return check


@router.post("/export")
def export_vault(
    payload: VaultExportRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> Response:
    """Download namespaces with their secrets, encrypted with a passphrase."""

    from datetime import date

    from lib.vault.portable import PortableVaultError, collect, seal

    _, _, user = record
    vault_manager, _ = _vault_components(request)
    namespaces = _readable_namespaces(request, user, payload.namespaces)
    try:
        data = seal(collect(vault_manager, namespaces, user.username), payload.passphrase)
    except PortableVaultError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except VaultError as exc:
        _raise_http_error(exc)
    name = namespaces[0].name if len(namespaces) == 1 else "entropy-vault"
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{name}-{date.today().isoformat()}.entvault"'
            ),
            "Cache-Control": "no-store",
        },
    )


@router.post("/import")
async def import_vault(
    request: Request,
    file: UploadFile = File(...),
    passphrase: str = Form(...),
    overwrite: bool = Form(False),
    namespaces: str = Form(""),
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """
    Restore an export into the current project: missing namespaces are
    created there, existing keys are kept unless `overwrite`. `namespaces`
    (comma separated) limits it.
    """

    from lib.vault.portable import MAX_FILE, PortableVaultError, restore, unseal

    _, _, user = record
    vault_manager, namespace_manager = _vault_components(request)
    project_id = _project_id(request)
    raw = await file.read(MAX_FILE + 1)
    try:
        payload = unseal(raw, passphrase)
    except PortableVaultError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    try:
        summary = restore(
            vault_manager,
            namespace_manager,
            payload,
            project_id=project_id,
            owner_user_id=user.id,
            can_create=_can(request, user, "vault.namespace.create", project_id),
            can_write=_may_write(request, user),
            overwrite=overwrite,
            only=[name.strip() for name in namespaces.split(",") if name.strip()],
        )
    except VaultError as exc:
        _raise_http_error(exc)
    return {
        **summary,
        "exported_by": payload.get("exported_by"),
        "exported_at": payload.get("exported_at"),
    }


# ---------------------------------------------------------------------
# Files (certificates, keystores, keys, ...)
# ---------------------------------------------------------------------


@router.post("/namespaces/{namespace_name}/files", status_code=201)
async def upload_file(
    namespace_name: str,
    request: Request,
    response: Response,
    key: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    sensitive: bool = Form(True),
    replace: bool = Form(False),
    record: SessionRecord = Depends(_current_session),
    _: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Keep a file in the vault (or replace the one under `key`)."""

    from lib.vault.files import MAX_FILE_BYTES, VaultFileError, make_value

    _, _, user = record
    vault_manager, namespace_manager = _vault_components(request)
    content = await file.read(MAX_FILE_BYTES + 1)
    try:
        value = make_value(file.filename or key, content, file.content_type)
    except VaultFileError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None

    try:
        namespace = _get_namespace(request, namespace_manager, namespace_name)
        exists = vault_manager.exists(namespace.id, key)
        if exists and not replace:
            raise VaultEntryExistsError(f"Vault entry '{key}' already exists.")
        _require(request, user, "vault.modify" if exists else "vault.add", namespace.project_id)
        store = vault_manager.update if exists else vault_manager.add
        entry = store(
            namespace_id=namespace.id,
            key=key,
            value=value,
            value_type=VaultValueType.FILE,
            sensitive=sensitive,
        )
    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"
    return {"entry": _entry_payload(vault_manager, namespace.id, entry)}


@router.get("/namespaces/{namespace_name}/entries/{key}/download")
def download_file(
    namespace_name: str,
    key: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """The file kept under `key`, as it was uploaded."""

    from lib.vault.files import content, safe_filename

    _, _, user = record
    vault_manager, namespace_manager = _vault_components(request)
    try:
        namespace = _get_namespace(request, namespace_manager, namespace_name)
        _require(request, user, "vault.read", namespace.project_id)
        entry = vault_manager.get_entry(namespace.id, key)
        if entry.type is not VaultValueType.FILE:
            raise HTTPException(status_code=422, detail=f"'{key}' is not a file.")
        value = vault_manager.get(namespace.id, key)
    except VaultError as exc:
        _raise_http_error(exc)

    filename = safe_filename(value["filename"]).replace('"', "")
    return Response(
        content=content(value),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
