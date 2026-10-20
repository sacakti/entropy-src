"""The read/write/delete/execute/all permission model and its migration."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.authorization.initializer import AuthorizationInitializer
from lib.authorization.service import AuthorizationService
from lib.database.connection import DatabaseConnection
from lib.database.objects.group_roles import GroupRolesTable
from lib.database.objects.groups import GroupsTable
from lib.database.objects.modules import ModulesTable
from lib.database.objects.permissions import PermissionsTable
from lib.database.objects.role_permissions import RolePermissionsTable
from lib.database.objects.roles import RolesTable
from lib.database.objects.user_groups import UserGroupsTable
from lib.database.objects.user_privileges import UserPrivilegesTable
from lib.database.objects.user_roles import UserRolesTable
from lib.database.objects.users import UsersTable

TABLES = (
    UsersTable,
    GroupsTable,
    ModulesTable,
    PermissionsTable,
    RolesTable,
    RolePermissionsTable,
    UserRolesTable,
    UserPrivilegesTable,
    UserGroupsTable,
    GroupRolesTable,
)


@pytest.fixture
def connection(tmp_path: Path) -> DatabaseConnection:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    for table in TABLES:
        table().create(connection)
    connection.commit()
    return connection


def _user(connection: DatabaseConnection, name: str) -> int:
    columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(users)")}
    values = {
        "username": name,
        "password_hash": "x",
        "full_name": name,
        "is_active": 1,
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }
    values = {key: value for key, value in values.items() if key in columns}
    cursor = connection.execute(
        f"INSERT INTO users ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
        tuple(values.values()),
    )
    connection.commit()
    return int(cursor.lastrowid)


def _grant_role(connection: DatabaseConnection, user_id: int, role: str) -> None:
    connection.execute(
        "INSERT INTO user_roles (user_id, role_id, created_at)"
        " SELECT ?, id, datetime('now') FROM roles WHERE name = ?",
        (user_id, role),
    )
    connection.commit()


def _role_permissions(connection: DatabaseConnection, role: str) -> set:
    return {
        row["name"]
        for row in connection.fetchall(
            "SELECT p.name FROM permissions p JOIN role_permissions rp ON rp.permission_id = p.id"
            " JOIN roles r ON r.id = rp.role_id WHERE r.name = ?",
            (role,),
        )
    }


def test_built_in_roles_follow_permission_types(connection) -> None:
    AuthorizationInitializer(connection).reconcile()

    assert _role_permissions(connection, "workflows-read") == {"workflows.read"}
    assert _role_permissions(connection, "workflows-write") == {"workflows.write"}
    assert _role_permissions(connection, "workflows-delete") == {"workflows.delete"}
    assert _role_permissions(connection, "workflows-execute") == {"workflows.execute"}
    assert "workflows.all" in _role_permissions(connection, "workflows-full")

    write = _role_permissions(connection, "write")
    delete = _role_permissions(connection, "delete")
    assert "vault.delete" not in write and "vault.delete" in delete
    assert {"nodes.delete", "schedules.delete", "users.delete", "plugins.delete"} <= delete


def test_all_grants_every_permission_of_its_module(connection) -> None:
    AuthorizationInitializer(connection).reconcile()
    user = _user(connection, "lead")
    connection.execute(
        "INSERT INTO user_privileges (user_id, permission_id, created_at)"
        " SELECT ?, id, datetime('now') FROM permissions WHERE name = 'workflows.all'",
        (user,),
    )
    connection.commit()
    service = AuthorizationService(connection)

    for name in ("workflows.read", "workflows.write", "workflows.delete", "workflows.execute"):
        assert service.has_permission(user, name)
    assert not service.has_permission(user, "plugins.read")
    assert {"workflows.delete", "workflows.execute"} <= set(service.permissions(user))


def test_old_grants_move_to_new_permissions(connection) -> None:
    # A database from before the change: old names, granted to a custom role.
    AuthorizationInitializer(connection).reconcile()
    connection.execute(
        "INSERT INTO permissions (module_id, name, description, permission_type)"
        " SELECT id, 'workflows.edit', 'Edit workflows.', 'write'"
        " FROM modules WHERE name = 'workflows'"
    )
    connection.execute(
        "INSERT INTO roles (name, description, created_at, updated_at)"
        " VALUES ('editors', 'Custom', datetime('now'), datetime('now'))"
    )
    connection.execute(
        "INSERT INTO role_permissions (role_id, permission_id, created_at)"
        " SELECT r.id, p.id, datetime('now') FROM roles r, permissions p"
        " WHERE r.name = 'editors' AND p.name = 'workflows.edit'"
    )
    connection.commit()
    user = _user(connection, "editor")
    _grant_role(connection, user, "editors")

    AuthorizationInitializer(connection).reconcile()

    service = AuthorizationService(connection)
    # Editing used to include deleting, so both are kept.
    assert _role_permissions(connection, "editors") == {"workflows.write", "workflows.delete"}
    assert service.has_permission(user, "workflows.write")
    assert connection.fetchone("SELECT 1 FROM permissions WHERE name = 'workflows.edit'") is None


def test_reader_cannot_write_or_delete(connection) -> None:
    AuthorizationInitializer(connection).reconcile()
    user = _user(connection, "reader")
    _grant_role(connection, user, "workflows-read")
    service = AuthorizationService(connection)

    assert service.has_permission(user, "workflows.read")
    assert not service.has_permission(user, "workflows.write")
    assert not service.has_permission(user, "workflows.delete")
    assert not service.has_permission(user, "workflows.execute")
