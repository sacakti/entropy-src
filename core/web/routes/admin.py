"""
Administration API: users, groups, roles and permissions.

Mutations go through the same managers as the `ent user`, `ent groups` and
`ent roles` commands, and require the same permissions.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import _require_permission
from lib.authorization.exceptions import (
    AuthGenericError,
    AuthorizationException,
    GroupNotFoundError,
    PermissionNotFoundError,
    RoleNotFoundError,
)
from lib.authorization.role_manager import ADMIN_ROLE
from lib.database.repositories.notifications import NotificationRepository, notify_user
from lib.models.session import Session
from lib.models.users import SYSTEM_USERNAME, User
from lib.users.exceptions import (
    InvalidUsernameError,
    PasswordReuseError,
    SystemUserError,
    UserAlreadyExistsError,
    UserError,
    UserNotFoundError,
    WeakPasswordError,
)

router = APIRouter(prefix="/api/admin", tags=["administration"])

SessionRecord = Tuple[Session, str, User]

ADMIN_READ_PERMISSIONS = ("users.read", "groups.read", "roles.read")


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    full_name: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=254)
    roles: List[str] = Field(default_factory=list)
    groups: List[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=254)


class PasswordSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Omit to generate a temporary password.
    password: Optional[str] = Field(default=None, max_length=256)


class NamedCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class NamedUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class NameList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    names: List[str] = Field(default_factory=list, max_length=1000)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _context(request: Request) -> Any:
    context = request.app.state.entropy_context

    if context is None or context.database_manager is None:
        raise HTTPException(status_code=503, detail="Entropy is unavailable.")

    return context


def _connection(request: Request) -> Any:
    return _context(request).database_manager.connection


def _require(request: Request, record: SessionRecord, permission: str) -> User:
    _, _, user = record
    _require_permission(request, user, permission)
    return user


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None

    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _http_error(exc: Exception) -> HTTPException:
    """Translate manager errors into HTTP responses."""

    if isinstance(
        exc,
        (UserNotFoundError, RoleNotFoundError, GroupNotFoundError, PermissionNotFoundError),
    ):
        return HTTPException(status_code=404, detail=str(exc))

    if isinstance(exc, UserAlreadyExistsError):
        return HTTPException(status_code=409, detail=str(exc))

    if isinstance(exc, (UserError, AuthorizationException)):
        return HTTPException(status_code=400, detail=str(exc))

    raise exc


def _names(rows: Iterable[Any], key: str = "name") -> Dict[int, List[str]]:
    grouped: Dict[int, List[str]] = {}

    for row in rows:
        grouped.setdefault(row["owner"], []).append(row[key])

    return grouped


def _notify_account(request: Request, actor: User, username: str, title: str, message: str, level: str = "info") -> None:
    """Tell a user about an administrator's change to their account."""

    if actor.username == username:
        return

    try:
        target = _context(request).user_manager.get(username)
    except UserError:
        return

    notify_user(_context(request), target.id, title, f"{message} (by {actor.username})", level, "administration")


def _sync(
    current: Iterable[str],
    wanted: Iterable[str],
    add: Any,
    remove: Any,
) -> None:
    """Apply the difference between two name sets."""

    current_set = set(current)
    wanted_set = {name.strip() for name in wanted if name.strip()}

    for name in sorted(wanted_set - current_set):
        add(name)

    for name in sorted(current_set - wanted_set):
        remove(name)


# ---------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------


@router.get("/summary")
def summary(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """Counts shown on the Administration overview."""

    _, _, user = record
    authorization = _context(request).authorization

    if user.id is None or authorization is None or not any(
        authorization.has_permission(user.id, permission)
        for permission in ADMIN_READ_PERMISSIONS
    ):
        raise HTTPException(status_code=403, detail="Permission denied.")

    connection = _connection(request)

    def count(sql: str) -> int:
        return int(connection.fetchone(sql)[0])

    response.headers["Cache-Control"] = "no-store"

    groups = [
        {"name": row["name"], "members": row["members"]}
        for row in connection.fetchall(
            """
            SELECT g.name, COUNT(ug.user_id) AS members
            FROM groups g LEFT JOIN user_groups ug ON ug.group_id = g.id
            GROUP BY g.id
            ORDER BY members DESC, g.name
            LIMIT 8
            """
        )
    ]

    roles = [
        {
            "name": row["name"],
            "users": row["users"],
            "groups": row["groups"],
            "permissions": row["permissions"],
        }
        for row in connection.fetchall(
            """
            SELECT r.name,
                   (SELECT COUNT(*) FROM user_roles ur WHERE ur.role_id = r.id) AS users,
                   (SELECT COUNT(*) FROM group_roles gr WHERE gr.role_id = r.id) AS groups,
                   (SELECT COUNT(*) FROM role_permissions rp WHERE rp.role_id = r.id) AS permissions
            FROM roles r
            ORDER BY users + groups DESC, permissions DESC, r.name
            LIMIT 8
            """
        )
    ]

    modules = [
        {
            "name": row["name"],
            "read": row["read"],
            "write": row["write"],
            "execute": row["execute"],
        }
        for row in connection.fetchall(
            """
            SELECT m.name,
                   SUM(p.permission_type = 'read') AS read,
                   SUM(p.permission_type = 'write') AS write,
                   SUM(p.permission_type = 'execute') AS execute
            FROM modules m JOIN permissions p ON p.module_id = m.id
            GROUP BY m.id
            ORDER BY COUNT(p.id) DESC, m.name
            """
        )
    ]

    return {
        "charts": {"groups": groups, "roles": roles, "modules": modules},
        "users": count("SELECT COUNT(*) FROM users"),
        "active_users": count("SELECT COUNT(*) FROM users WHERE is_active = 1"),
        "groups": count("SELECT COUNT(*) FROM groups"),
        "roles": count("SELECT COUNT(*) FROM roles"),
        "permissions": count("SELECT COUNT(*) FROM permissions"),
        "modules": count("SELECT COUNT(*) FROM modules"),
    }


# ---------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------


def _user_payloads(request: Request) -> List[dict]:
    connection = _connection(request)

    roles = _names(
        connection.fetchall(
            """
            SELECT ur.user_id AS owner, r.name
            FROM user_roles ur JOIN roles r ON r.id = ur.role_id
            ORDER BY r.name
            """
        )
    )
    groups = _names(
        connection.fetchall(
            """
            SELECT ug.user_id AS owner, g.name
            FROM user_groups ug JOIN groups g ON g.id = ug.group_id
            ORDER BY g.name
            """
        )
    )

    return [
        {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "is_active": user.is_active,
            "is_system": user.username == SYSTEM_USERNAME,
            "created_at": _iso(user.created_at),
            "updated_at": _iso(user.updated_at),
            "roles": roles.get(user.id, []),
            "groups": groups.get(user.id, []),
        }
        for user in sorted(
            _context(request).user_manager.list(),
            key=lambda item: item.username.casefold(),
        )
    ]


def _user_payload(request: Request, username: str) -> dict:
    for item in _user_payloads(request):
        if item["username"] == username:
            return item

    raise HTTPException(status_code=404, detail=f"User '{username}' does not exist.")


@router.get("/users")
def list_users(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "users.read")
    response.headers["Cache-Control"] = "no-store"
    return {"items": _user_payloads(request)}


@router.post("/users", status_code=201, dependencies=[Depends(verify_csrf)])
def create_user(
    payload: UserCreate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "users.create")

    if payload.roles:
        _require(request, record, "users.roles")

    if payload.groups:
        _require(request, record, "groups.users")

    context = _context(request)

    try:
        user = context.user_manager.create(
            username=payload.username,
            password=payload.password,
            full_name=payload.full_name,
            email=payload.email,
        )

        for role in payload.roles:
            context.user_role_manager.add_role(user, role)

        for group in payload.groups:
            context.group_manager.add_user(context.group_manager.get(group), user.username)
    except (UserError, AuthorizationException) as exc:
        raise _http_error(exc) from None

    return _user_payload(request, user.username)


@router.patch("/users/{username}", dependencies=[Depends(verify_csrf)])
def update_user(
    username: str,
    payload: UserUpdate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "users.modify")
    manager = _context(request).user_manager

    try:
        user = manager.get(username)
        manager.update_profile(
            user,
            (payload.full_name or "").strip() or None,
            (payload.email or "").strip() or None,
        )
    except UserError as exc:
        raise _http_error(exc) from None

    return _user_payload(request, username)


@router.post("/users/{username}/{state}", dependencies=[Depends(verify_csrf)])
def set_user_active(
    username: str,
    state: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    if state not in ("enable", "disable"):
        raise HTTPException(status_code=404, detail="Not Found")

    actor = _require(request, record, f"users.{state}")

    if state == "disable" and actor.username == username:
        raise HTTPException(status_code=400, detail="You cannot disable your own account.")

    try:
        _context(request).user_manager.set_active(username, state == "enable")
    except (UserError, SystemUserError) as exc:
        raise _http_error(exc) from None

    if state == "enable":
        _notify_account(request, actor, username, "Your account was enabled", "You can sign in again.", "success")

    return _user_payload(request, username)


@router.put("/users/{username}/password", dependencies=[Depends(verify_csrf)])
def set_user_password(
    username: str,
    payload: PasswordSet,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """Set a password, or generate a temporary one when none is given."""

    actor = _require(request, record, "users.modify")
    manager = _context(request).user_manager

    try:
        user = manager.get(username)

        if payload.password:
            manager.admin_change_password(user, payload.password)
            password = None
        else:
            _, password = manager.reset_password(user)
    except (WeakPasswordError, PasswordReuseError, UserError) as exc:
        raise _http_error(exc) from None

    _notify_account(
        request,
        actor,
        username,
        "Your password was changed",
        "An administrator set a new password for your account.",
        "warning",
    )

    if password is None:
        return {"message": f"Password updated for '{username}'.", "password": None}

    return {
        "message": f"Temporary password generated for '{username}'.",
        "password": password,
    }


@router.delete("/users/{username}", dependencies=[Depends(verify_csrf)])
def delete_user(
    username: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    actor = _require(request, record, "users.delete")

    if actor.username == username:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    context = _context(request)

    try:
        user = context.user_manager.get(username)
        context.user_manager.delete(user)
    except (UserError, SystemUserError) as exc:
        raise _http_error(exc) from None

    # Foreign keys are not enforced, so clear what referenced the user.
    with context.database_manager.connection.transaction() as connection:
        for table in ("user_roles", "user_groups"):
            connection.execute(f"DELETE FROM {table} WHERE user_id = ?", (user.id,))

    NotificationRepository(context.database_manager.connection).delete(user.id)

    return {"message": f"User '{username}' deleted."}


@router.put("/users/{username}/roles", dependencies=[Depends(verify_csrf)])
def set_user_roles(
    username: str,
    payload: NameList,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    actor = _require(request, record, "users.roles")
    context = _context(request)

    try:
        user = context.user_manager.get(username)
        _sync(
            [role.name for role in context.user_role_manager.roles(user)],
            payload.names,
            lambda name: context.user_role_manager.add_role(user, name),
            lambda name: context.user_role_manager.revoke_role(user, name),
        )
    except (UserError, AuthorizationException) as exc:
        raise _http_error(exc) from None

    roles = ", ".join(sorted(payload.names)) or "none"
    _notify_account(request, actor, username, "Your roles changed", f"Your roles are now: {roles}.")

    return _user_payload(request, username)


@router.put("/users/{username}/groups", dependencies=[Depends(verify_csrf)])
def set_user_groups(
    username: str,
    payload: NameList,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "groups.users")
    context = _context(request)
    groups = context.group_manager

    try:
        user = context.user_manager.get(username)
        current = [
            row["name"]
            for row in context.database_manager.connection.fetchall(
                """
                SELECT g.name FROM user_groups ug JOIN groups g ON g.id = ug.group_id
                WHERE ug.user_id = ?
                """,
                (user.id,),
            )
        ]
        _sync(
            current,
            payload.names,
            lambda name: groups.add_user(groups.get(name), username),
            lambda name: groups.remove_user(groups.get(name), username),
        )
    except (UserError, AuthorizationException) as exc:
        raise _http_error(exc) from None

    return _user_payload(request, username)


# ---------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------


def _group_payloads(request: Request) -> List[dict]:
    connection = _connection(request)

    users = _names(
        connection.fetchall(
            """
            SELECT ug.group_id AS owner, u.username AS name
            FROM user_groups ug JOIN users u ON u.id = ug.user_id
            ORDER BY u.username
            """
        )
    )
    roles = _names(
        connection.fetchall(
            """
            SELECT gr.group_id AS owner, r.name
            FROM group_roles gr JOIN roles r ON r.id = gr.role_id
            ORDER BY r.name
            """
        )
    )

    return [
        {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "created_at": _iso(group.created_at),
            "updated_at": _iso(group.updated_at),
            "users": users.get(group.id, []),
            "roles": roles.get(group.id, []),
        }
        for group in sorted(
            _context(request).group_manager.list(),
            key=lambda item: item.name.casefold(),
        )
    ]


def _group_payload(request: Request, name: str) -> dict:
    for item in _group_payloads(request):
        if item["name"] == name:
            return item

    raise HTTPException(status_code=404, detail=f"Group '{name}' does not exist.")


@router.get("/groups")
def list_groups(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "groups.read")
    response.headers["Cache-Control"] = "no-store"
    return {"items": _group_payloads(request)}


@router.post("/groups", status_code=201, dependencies=[Depends(verify_csrf)])
def create_group(
    payload: NamedCreate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "groups.create")

    try:
        group = _context(request).group_manager.create(payload.name, payload.description)
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    return _group_payload(request, group.name)


@router.patch("/groups/{name}", dependencies=[Depends(verify_csrf)])
def update_group(
    name: str,
    payload: NamedUpdate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "groups.modify")
    manager = _context(request).group_manager

    try:
        group = manager.modify(
            manager.get(name),
            name=payload.name,
            description=payload.description,
        )
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    return _group_payload(request, group.name)


@router.delete("/groups/{name}", dependencies=[Depends(verify_csrf)])
def delete_group(
    name: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "groups.delete")
    context = _context(request)

    try:
        group = context.group_manager.get(name)
        context.group_manager.delete(group)
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    with context.database_manager.connection.transaction() as connection:
        for table in ("user_groups", "group_roles"):
            connection.execute(f"DELETE FROM {table} WHERE group_id = ?", (group.id,))

    return {"message": f"Group '{name}' deleted."}


@router.put("/groups/{name}/users", dependencies=[Depends(verify_csrf)])
def set_group_users(
    name: str,
    payload: NameList,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "groups.users")
    manager = _context(request).group_manager

    try:
        group = manager.get(name)
        _sync(
            [user.username for user in manager.users(group)],
            payload.names,
            lambda username: manager.add_user(group, username),
            lambda username: manager.remove_user(group, username),
        )
    except (UserError, AuthorizationException) as exc:
        raise _http_error(exc) from None

    return _group_payload(request, name)


@router.put("/groups/{name}/roles", dependencies=[Depends(verify_csrf)])
def set_group_roles(
    name: str,
    payload: NameList,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "groups.roles")
    manager = _context(request).group_manager

    try:
        group = manager.get(name)
        _sync(
            [role.name for role in manager.roles(group)],
            payload.names,
            lambda role: manager.grant_role(group, role),
            lambda role: manager.revoke_role(group, role),
        )
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    return _group_payload(request, name)


# ---------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------


def _role_payloads(request: Request) -> List[dict]:
    connection = _connection(request)

    permissions = _names(
        connection.fetchall(
            """
            SELECT rp.role_id AS owner, p.name
            FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
            ORDER BY p.name
            """
        )
    )
    users = _names(
        connection.fetchall(
            """
            SELECT ur.role_id AS owner, u.username AS name
            FROM user_roles ur JOIN users u ON u.id = ur.user_id
            ORDER BY u.username
            """
        )
    )
    groups = _names(
        connection.fetchall(
            """
            SELECT gr.role_id AS owner, g.name
            FROM group_roles gr JOIN groups g ON g.id = gr.group_id
            ORDER BY g.name
            """
        )
    )

    return [
        {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "is_builtin": role.name == ADMIN_ROLE,
            "created_at": _iso(role.created_at),
            "updated_at": _iso(role.updated_at),
            "permissions": permissions.get(role.id, []),
            "users": users.get(role.id, []),
            "groups": groups.get(role.id, []),
        }
        for role in sorted(
            _context(request).role_manager.list(),
            key=lambda item: item.name.casefold(),
        )
    ]


def _role_payload(request: Request, name: str) -> dict:
    for item in _role_payloads(request):
        if item["name"] == name:
            return item

    raise HTTPException(status_code=404, detail=f"Role '{name}' does not exist.")


@router.get("/roles")
def list_roles(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "roles.read")
    response.headers["Cache-Control"] = "no-store"
    return {"items": _role_payloads(request)}


@router.post("/roles", status_code=201, dependencies=[Depends(verify_csrf)])
def create_role(
    payload: NamedCreate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "roles.create")

    try:
        role = _context(request).role_manager.create(payload.name, payload.description)
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    return _role_payload(request, role.name)


@router.patch("/roles/{name}", dependencies=[Depends(verify_csrf)])
def update_role(
    name: str,
    payload: NamedUpdate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "roles.modify")
    manager = _context(request).role_manager

    try:
        role = manager.modify(
            manager.get(name),
            name=payload.name,
            description=payload.description,
        )
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    return _role_payload(request, role.name)


@router.delete("/roles/{name}", dependencies=[Depends(verify_csrf)])
def delete_role(
    name: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "roles.delete")
    context = _context(request)

    try:
        role = context.role_manager.get(name)
        context.role_manager.delete(role)
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    with context.database_manager.connection.transaction() as connection:
        for table in ("user_roles", "group_roles", "role_permissions"):
            connection.execute(f"DELETE FROM {table} WHERE role_id = ?", (role.id,))

    return {"message": f"Role '{name}' deleted."}


@router.put("/roles/{name}/permissions", dependencies=[Depends(verify_csrf)])
def set_role_permissions(
    name: str,
    payload: NameList,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "roles.permissions")
    manager = _context(request).role_manager

    try:
        role = manager.get(name)
        _sync(
            [permission.name for permission in manager.permissions(role)],
            payload.names,
            lambda permission: manager.grant_permission(role, permission),
            lambda permission: manager.revoke_permission(role, permission),
        )
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    return _role_payload(request, name)


# ---------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------


@router.get("/permissions")
def list_permissions(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """Every permission grouped by module, with the roles that hold it."""

    _require(request, record, "roles.read")
    connection = _connection(request)

    roles = _names(
        connection.fetchall(
            """
            SELECT rp.permission_id AS owner, r.name
            FROM role_permissions rp JOIN roles r ON r.id = rp.role_id
            ORDER BY r.name
            """
        )
    )

    modules: Dict[str, dict] = {}

    for row in connection.fetchall(
        """
        SELECT p.id, p.name, p.description, p.permission_type,
               m.name AS module, m.description AS module_description
        FROM permissions p JOIN modules m ON m.id = p.module_id
        ORDER BY m.name, p.name
        """
    ):
        module = modules.setdefault(
            row["module"],
            {"name": row["module"], "description": row["module_description"], "permissions": []},
        )
        module["permissions"].append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "type": row["permission_type"],
                "roles": roles.get(row["id"], []),
            }
        )

    response.headers["Cache-Control"] = "no-store"

    return {"modules": list(modules.values())}


@router.put("/permissions/{name}/roles", dependencies=[Depends(verify_csrf)])
def set_permission_roles(
    name: str,
    payload: NameList,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """Choose which roles hold one permission."""

    _require(request, record, "roles.permissions")
    connection = _connection(request)
    manager = _context(request).role_manager

    current = [
        row["name"]
        for row in connection.fetchall(
            """
            SELECT r.name FROM role_permissions rp
            JOIN roles r ON r.id = rp.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE p.name = ?
            """,
            (name,),
        )
    ]

    if ADMIN_ROLE in set(current) ^ {item.strip() for item in payload.names}:
        raise HTTPException(
            status_code=400,
            detail=str(AuthGenericError("The built-in 'admin' role cannot be modified.")),
        )

    try:
        _sync(
            current,
            payload.names,
            lambda role: manager.grant_permission(manager.get(role), name),
            lambda role: manager.revoke_permission(manager.get(role), name),
        )
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    return {"name": name, "roles": sorted({item.strip() for item in payload.names if item.strip()})}
