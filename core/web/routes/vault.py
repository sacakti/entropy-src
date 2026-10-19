"""
Vault namespace and secret management API.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from pydantic import BaseModel, Field

from core.web.routes.auth import _current_session
from core.web.routes.workflows import _require_permission
from lib.database.repositories.notifications import notify_user
from lib.models.authorization import VaultAccess, VaultVisibility
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
    visibility: VaultVisibility = VaultVisibility.PRIVATE


class NamespaceUpdateRequest(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    visibility: Optional[VaultVisibility] = None


class EntryCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    value: Any
    type: VaultValueType = VaultValueType.STRING
    sensitive: bool = True


class EntryUpdateRequest(BaseModel):
    value: Any
    type: VaultValueType = VaultValueType.STRING
    sensitive: bool = True


class AccessGrantRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    access: VaultAccess


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
    access: Optional[VaultAccess] = None,
) -> dict[str, Any]:
    return {
        "id": namespace.id,
        # The caller's effective access; null for shared read-only access.
        "access": access.value if access is not None else None,
        "name": namespace.name,
        "owner_user_id": namespace.owner_user_id,
        "visibility": namespace.visibility.value,
        "created_at": (
            namespace.created_at.isoformat()
            if namespace.created_at
            else None
        ),
        "updated_at": (
            namespace.updated_at.isoformat()
            if namespace.updated_at
            else None
        ),
    }


def _entry_metadata(entry: Any) -> dict[str, Any]:
    """Return metadata only; never serialize the stored value."""
    return {
        "id": entry.id,
        "key": entry.key,
        "type": entry.type.value,
        "sensitive": entry.sensitive,
        "created_at": (
            entry.created_at.isoformat()
            if entry.created_at
            else None
        ),
        "updated_at": (
            entry.updated_at.isoformat()
            if entry.updated_at
            else None
        ),
    }


def _users_by_id(request: Request) -> dict[int, User]:
    """Every user keyed by id, for labelling assignments."""
    user_manager = getattr(request.app.state.entropy_context, "user_manager", None)

    if user_manager is None:
        return {}

    return {
        account.id: account
        for account in user_manager.list()
        if account.id is not None
    }


def _users_by_name(request: Request) -> dict[str, User]:
    return {account.username: account for account in _users_by_id(request).values()}


def _access_payload(
    assignment: Any,
    users: Optional[dict[int, User]] = None,
) -> dict[str, Any]:
    account = (users or {}).get(assignment.user_id)

    return {
        "id": assignment.id,
        "namespace_id": assignment.namespace_id,
        "user_id": assignment.user_id,
        "username": account.username if account else None,
        "full_name": account.full_name if account else None,
        "access": assignment.access.value,
        "created_at": (
            assignment.created_at.isoformat()
            if assignment.created_at
            else None
        ),
    }


# ---------------------------------------------------------------------
# Namespace authorization
# ---------------------------------------------------------------------


_ACCESS_LEVEL = {
    VaultAccess.READ: 1,
    VaultAccess.WRITE: 2,
    VaultAccess.ADMIN: 3,
}


def _has_permission(request: Request, user: User, permission: str) -> bool:
    authorization = request.app.state.entropy_context.authorization

    return bool(
        authorization is not None
        and user.id is not None
        and authorization.has_permission(user.id, permission)
    )


def _require_namespace_access(
    request: Request,
    namespace_manager: Any,
    namespace: Any,
    user: User,
    required: VaultAccess,
    permission: str,
) -> None:
    """
    Enforce access to a specific namespace.

    Access granted on the namespace itself (or ownership) is sufficient:
    a namespace administrator who grants a user READ or WRITE has decided
    that user may work with it. Without a grant, shared namespaces are
    readable by users holding the role permission for the operation.
    """
    if namespace.id is None:
        raise HTTPException(
            status_code=404,
            detail="Vault namespace not found.",
        )

    access = namespace_manager.access_by_user_id(
        namespace,
        user.id,
    )

    if access is not None and _ACCESS_LEVEL[access] >= _ACCESS_LEVEL[required]:
        return

    if (
        access is None
        and namespace.visibility == VaultVisibility.SHARED
        and required == VaultAccess.READ
        and _has_permission(request, user, permission)
    ):
        return

    if access is None:
        detail = f"You have no access to the '{namespace.name}' namespace."
    else:
        detail = (
            f"This needs {required.value} access to the '{namespace.name}' "
            f"namespace; you have {access.value} access."
        )

    raise HTTPException(status_code=403, detail=detail)


def _get_namespace(
    namespace_manager: Any,
    namespace_name: str,
) -> Any:
    try:
        return namespace_manager.get(namespace_name)
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
    """List namespaces visible to the authenticated user."""
    _, _, user = record
    # Namespaces granted to the user are always listed; shared ones need
    # the role permission.
    can_browse_shared = _has_permission(request, user, "vault.namespace.read")

    _, namespace_manager = _vault_components(request)

    try:
        namespaces = namespace_manager.list()
        visible = []

        for namespace in namespaces:
            access = namespace_manager.access_by_user_id(
                namespace,
                user.id,
            )

            if access is not None:
                visible.append((namespace, access))
            elif (
                namespace.visibility == VaultVisibility.SHARED
                and can_browse_shared
            ):
                visible.append((namespace, None))

    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    return {
        "items": [
            _namespace_payload(namespace, access)
            for namespace, access in visible
        ]
    }


@router.post("/namespaces", status_code=201)
def create_namespace(
    payload: NamespaceCreateRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """Create a namespace owned by the authenticated user."""
    _, _, user = record
    _require_permission(request, user, "vault.namespace.create")

    _, namespace_manager = _vault_components(request)

    try:
        namespace = namespace_manager.create(
            name=payload.name.strip(),
            owner_user_id=user.id,
            visibility=payload.visibility,
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
    """Rename a namespace or update its visibility."""
    _, _, user = record

    _, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.ADMIN,
            "vault.namespace.modify",
        )

        namespace = namespace_manager.modify(
            namespace,
            name=payload.name,
            visibility=payload.visibility,
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
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.ADMIN,
            "vault.namespace.delete",
        )

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
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.READ,
            "vault.read",
        )

        if namespace.id is None:
            raise HTTPException(
                status_code=404,
                detail="Vault namespace not found.",
            )

        entries = vault_manager.list(namespace.id)

    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    return {
        "items": [
            _entry_metadata(entry)
            for entry in entries
        ]
    }


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
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.WRITE,
            "vault.add",
        )

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
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.WRITE,
            "vault.modify",
        )

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
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.READ,
            "vault.read",
        )

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

    return {
        "entry": {
            **_entry_metadata(entry),
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
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.WRITE,
            "vault.delete",
        )

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
# Namespace access grants
# ---------------------------------------------------------------------


@router.get("/namespaces/{namespace_name}/access")
def list_namespace_access(
    namespace_name: str,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """List explicit access assignments."""
    _, _, user = record

    _, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.ADMIN,
            "vault.namespace.users",
        )

        assignments = namespace_manager.access_assignments(
            namespace,
        )

    except VaultError as exc:
        _raise_http_error(exc)

    response.headers["Cache-Control"] = "no-store"

    users = _users_by_id(request)

    return {
        "items": [
            _access_payload(assignment, users)
            for assignment in assignments
        ]
    }


@router.get("/users")
def suggest_users(
    request: Request,
    response: Response,
    q: str = Query(default="", max_length=100),
    record: SessionRecord = Depends(_current_session),
) -> dict[str, Any]:
    """Active users matching a username, name or id, for access grants."""
    _, _, user = record

    # Namespace administrators may grant access without the role permission.
    if not _has_permission(request, user, "vault.namespace.users"):
        _, namespace_manager = _vault_components(request)

        if not any(
            namespace_manager.access_by_user_id(namespace, user.id) == VaultAccess.ADMIN
            for namespace in namespace_manager.list()
        ):
            raise HTTPException(status_code=403, detail="Permission denied.")

    search = q.strip().casefold()
    matches = []

    for account in sorted(
        _users_by_id(request).values(),
        key=lambda item: item.username.casefold(),
    ):
        if not account.is_active:
            continue

        if search and not (
            search in account.username.casefold()
            or search in (account.full_name or "").casefold()
            or search == str(account.id)
        ):
            continue

        matches.append(
            {
                "id": account.id,
                "username": account.username,
                "full_name": account.full_name,
            }
        )

        if len(matches) == 8:
            break

    response.headers["Cache-Control"] = "no-store"

    return {"items": matches}


@router.post(
    "/namespaces/{namespace_name}/access",
    status_code=204,
)
def grant_namespace_access(
    namespace_name: str,
    payload: AccessGrantRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """Grant a user READ, WRITE, or ADMIN access."""
    _, _, user = record

    _, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.ADMIN,
            "vault.namespace.users",
        )

        namespace_manager.grant_access(
            namespace,
            payload.username.strip(),
            payload.access,
        )

        if payload.username.strip() != user.username:
            target = _users_by_name(request).get(payload.username.strip())
            notify_user(
                request.app.state.entropy_context,
                target.id if target else None,
                f"Vault access: {namespace.name}",
                f"{user.username} gave you {payload.access.value} access to the '{namespace.name}' namespace.",
                "info",
                "vault",
            )

    except VaultError as exc:
        _raise_http_error(exc)

    return Response(
        status_code=204,
        headers={"Cache-Control": "no-store"},
    )


@router.delete(
    "/namespaces/{namespace_name}/access/{username}",
    status_code=204,
)
def revoke_namespace_access(
    namespace_name: str,
    username: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """Revoke an explicit user access assignment."""
    _, _, user = record

    _, namespace_manager = _vault_components(request)

    try:
        namespace = _get_namespace(
            namespace_manager,
            namespace_name,
        )

        _require_namespace_access(
            request,
            namespace_manager,
            namespace,
            user,
            VaultAccess.ADMIN,
            "vault.namespace.users",
        )

        namespace_manager.revoke_access(
            namespace,
            username,
        )

        if username != user.username:
            target = _users_by_name(request).get(username)
            notify_user(
                request.app.state.entropy_context,
                target.id if target else None,
                f"Vault access removed: {namespace.name}",
                f"{user.username} removed your access to the '{namespace.name}' namespace.",
                "warning",
                "vault",
            )

    except VaultError as exc:
        _raise_http_error(exc)

    return Response(
        status_code=204,
        headers={"Cache-Control": "no-store"},
    )
