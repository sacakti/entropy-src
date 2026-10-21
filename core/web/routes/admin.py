"""
Administration API: users, groups, roles and permissions.

Mutations go through the same managers as the `ent user`, `ent groups` and
`ent roles` commands, and require the same permissions.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.workflows import _require_permission
from lib.authorization.exceptions import (
    AuthorizationException,
    GroupNotFoundError,
    PermissionNotFoundError,
    RoleNotFoundError,
)
from lib.database.repositories.notifications import NotificationRepository, notify_user
from lib.models.session import Session
from lib.models.users import SYSTEM_USERNAME, User
from lib.users.exceptions import (
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


class RoleCreate(NamedCreate):
    title: Optional[str] = Field(default=None, max_length=100)
    # Where the role applies: everywhere, or in the projects it is given in.
    scope: Literal["global", "project"] = "project"


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    title: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class Membership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str = Field(min_length=1, max_length=40)
    role: str = Field(min_length=1, max_length=100)


class MembershipList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memberships: List[Membership] = Field(default_factory=list, max_length=1000)


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
            "delete": row["delete_count"],
            "full": row["full_count"],
        }
        for row in connection.fetchall(
            """
            SELECT m.name,
                   SUM(p.permission_type = 'read') AS read,
                   SUM(p.permission_type = 'write') AS write,
                   SUM(p.permission_type = 'execute') AS execute,
                   SUM(p.permission_type = 'delete') AS delete_count,
                   SUM(p.permission_type = 'full') AS full_count
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
    projects = _memberships(connection, "user_id")

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
            # Project roles given to the user directly (groups add their own).
            "projects": projects.get(user.id, []),
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
    _check_global_roles(_connection(request), payload.names)

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
    projects = _memberships(connection, "group_id")

    return [
        {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "created_at": _iso(group.created_at),
            "updated_at": _iso(group.updated_at),
            "users": users.get(group.id, []),
            "roles": roles.get(group.id, []),
            "projects": projects.get(group.id, []),
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
    _check_global_roles(_connection(request), payload.names)
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


def _role_rows(connection: Any) -> Dict[str, Any]:
    """Scope, title and built-in flag of every role, by name."""

    return {
        row["name"]: row
        for row in connection.fetchall("SELECT name, scope, builtin, title FROM roles")
    }


def _check_global_roles(connection: Any, names: List[str]) -> None:
    """Users and groups hold global roles directly; project roles via projects."""

    rows = _role_rows(connection)
    project_roles = [name for name in names if name in rows and rows[name]["scope"] == "project"]
    if project_roles:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{', '.join(project_roles)}: project roles are given in a project"
                " (Projects, or the user's project memberships)."
            ),
        )


def _set_memberships(
    request: Request, kind: str, principal: str, memberships: List[Membership]
) -> None:
    """Replace a user's or group's project roles across all projects."""

    from lib.authorization.projects import Projects

    connection = _connection(request)
    store = Projects(connection)
    column = "group_id" if kind == "group" else "user_id"
    table, key = ("groups", "name") if kind == "group" else ("users", "username")
    row = connection.fetchone(f"SELECT id FROM {table} WHERE {key} = ?", (principal,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"{kind.title()} '{principal}' does not exist.")
    wanted = []
    for item in memberships:
        project = store.get(item.project)
        if project is None:
            raise HTTPException(status_code=422, detail=f"Project '{item.project}' not found.")
        role = connection.fetchone("SELECT id, scope FROM roles WHERE name = ?", (item.role,))
        if role is None or role["scope"] != "project":
            raise HTTPException(
                status_code=422, detail=f"'{item.role}' is not a project role."
            )
        wanted.append((project["id"], role["id"]))
    with connection.transaction():
        connection.execute(f"DELETE FROM project_members WHERE {column} = ?", (row["id"],))
        for project_id, role_id in dict.fromkeys(wanted):
            connection.execute(
                f"INSERT OR IGNORE INTO project_members (project_id, {column}, role_id,"
                " created_at) VALUES (?, ?, ?, datetime('now'))",
                (project_id, row["id"], role_id),
            )


def _memberships(connection: Any, column: str) -> Dict[int, List[dict]]:
    found: Dict[int, List[dict]] = {}
    for row in connection.fetchall(
        f"""
        SELECT pm.{column} AS owner, p.key AS project, p.name AS project_name,
               r.name AS role, COALESCE(r.title, r.name) AS role_title
        FROM project_members pm
        JOIN projects p ON p.id = pm.project_id
        JOIN roles r ON r.id = pm.role_id
        WHERE pm.{column} IS NOT NULL
        ORDER BY p.name, r.name
        """
    ):
        found.setdefault(row["owner"], []).append(
            {
                "project": row["project"],
                "project_name": row["project_name"],
                "role": row["role"],
                "role_title": row["role_title"],
            }
        )
    return found


def _role_payloads(request: Request) -> List[dict]:
    connection = _connection(request)
    extras = _role_rows(connection)
    in_projects = {
        row["role_id"]: int(row["n"])
        for row in connection.fetchall(
            "SELECT role_id, COUNT(*) AS n FROM project_members GROUP BY role_id"
        )
    }

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
            "title": (extras[role.name]["title"] if role.name in extras else None) or role.name,
            "scope": extras[role.name]["scope"] if role.name in extras else "global",
            "is_builtin": bool(extras[role.name]["builtin"]) if role.name in extras else False,
            # How many project memberships use it.
            "project_members": in_projects.get(role.id, 0),
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


def _refuse_builtin(request: Request, name: str) -> None:
    row = _role_rows(_connection(request)).get(name)
    if row is not None and row["builtin"]:
        raise HTTPException(
            status_code=409,
            detail=f"'{name}' is a built-in role and cannot be changed; create a custom role.",
        )


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
    payload: RoleCreate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "roles.create")

    try:
        role = _context(request).role_manager.create(payload.name, payload.description)
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    with _connection(request).transaction() as connection:
        connection.execute(
            "UPDATE roles SET scope = ?, title = ?, builtin = 0 WHERE id = ?",
            (payload.scope, (payload.title or "").strip() or role.name, role.id),
        )

    return _role_payload(request, role.name)


@router.patch("/roles/{name}", dependencies=[Depends(verify_csrf)])
def update_role(
    name: str,
    payload: RoleUpdate,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "roles.modify")
    _refuse_builtin(request, name)
    manager = _context(request).role_manager

    try:
        role = manager.modify(
            manager.get(name),
            name=payload.name,
            description=payload.description,
        )
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    if payload.title is not None:
        with _connection(request).transaction() as connection:
            connection.execute(
                "UPDATE roles SET title = ? WHERE id = ?",
                (payload.title.strip() or role.name, role.id),
            )

    return _role_payload(request, role.name)


@router.delete("/roles/{name}", dependencies=[Depends(verify_csrf)])
def delete_role(
    name: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    _require(request, record, "roles.delete")
    _refuse_builtin(request, name)
    context = _context(request)

    try:
        role = context.role_manager.get(name)
        context.role_manager.delete(role)
    except AuthorizationException as exc:
        raise _http_error(exc) from None

    with context.database_manager.connection.transaction() as connection:
        for table in ("user_roles", "group_roles", "role_permissions", "project_members"):
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
    _refuse_builtin(request, name)
    manager = _context(request).role_manager

    from lib.authorization.projects import PROJECT_PERMISSIONS

    row = _role_rows(_connection(request)).get(name)
    if row is not None and row["scope"] == "project":
        outside = sorted(set(payload.names) - PROJECT_PERMISSIONS)
        if outside:
            raise HTTPException(
                status_code=422,
                detail=f"A project role cannot hold {', '.join(outside)}; make it a global role.",
            )

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
    from lib.authorization.projects import PROJECT_PERMISSIONS

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
                # May be part of a project role (else only of global roles).
                "project": row["name"] in PROJECT_PERMISSIONS,
            }
        )

    response.headers["Cache-Control"] = "no-store"

    return {"modules": list(modules.values())}


@router.put("/users/{username}/projects", dependencies=[Depends(verify_csrf)])
def set_user_projects(
    username: str,
    payload: MembershipList,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """The user's roles in each project."""

    actor = _require(request, record, "projects.manage")
    _set_memberships(request, "user", username, payload.memberships)
    summary = ", ".join(f"{item.role} in {item.project}" for item in payload.memberships) or "none"
    _notify_account(
        request, actor, username, "Your projects changed", f"Your project roles: {summary}."
    )
    return _user_payload(request, username)


@router.put("/groups/{name}/projects", dependencies=[Depends(verify_csrf)])
def set_group_projects(
    name: str,
    payload: MembershipList,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> dict:
    """The group's roles in each project (every member gets them)."""

    _require(request, record, "projects.manage")
    _set_memberships(request, "group", name, payload.memberships)
    return _group_payload(request, name)
