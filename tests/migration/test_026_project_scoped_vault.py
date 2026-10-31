"""Migration 026: project scoped Vault, access from project roles only."""

from __future__ import annotations

import importlib

import pytest

from lib.authorization.projects import Projects, default_project_id
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

Migration = importlib.import_module(
    "lib.migrations.scripts.026_project_scoped_vault"
).ProjectScopedVaultMigration

NOW = "2026-01-01T00:00:00"


@pytest.fixture
def connection(tmp_path):
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.open()
    for table in (
        GroupsTable,
        RolesTable,
        ModulesTable,
        PermissionsTable,
        UserGroupsTable,
        UserRolesTable,
        GroupRolesTable,
        RolePermissionsTable,
        UserPrivilegesTable,
    ):
        table().create(connection)

    # The Vault tables as they were before migration 026.
    connection.execute(
        """
        CREATE TABLE vault_namespaces
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            owner_user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
            visibility TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE vault_entries
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace_id INTEGER NOT NULL
                REFERENCES vault_namespaces (id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            type TEXT NOT NULL,
            sensitive INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE TABLE vault_namespace_access (id INTEGER PRIMARY KEY, namespace_id INTEGER,"
        " user_id INTEGER, access TEXT, created_at TEXT)"
    )
    connection.execute(
        "CREATE TABLE vault_namespace_projects (namespace_id INTEGER PRIMARY KEY,"
        " project_id INTEGER NOT NULL)"
    )
    connection.commit()
    yield connection
    connection.close()


def _id(connection, sql: str, parameters: tuple) -> int:
    return int(connection.execute(sql, parameters).lastrowid)


def _seed(connection) -> dict:
    alpha = Projects(connection).create("alpha", "Alpha", "", "admin")["id"]
    default = default_project_id(connection)

    module = _id(
        connection,
        "INSERT INTO modules (name, description) VALUES ('vault', '')",
        (),
    )
    permissions = {
        name: _id(
            connection,
            "INSERT INTO permissions (module_id, name, permission_type, description)"
            " VALUES (?, ?, 'read', '')",
            (module, name),
        )
        for name in ("vault.read", "vault.add", "vault.namespace.users", "workflows.read")
    }

    def role(name: str, scope: str, *granted: str) -> int:
        role_id = _id(
            connection,
            "INSERT INTO roles (name, description, scope, created_at, updated_at)"
            " VALUES (?, '', ?, ?, ?)",
            (name, scope, NOW, NOW),
        )
        for permission in granted:
            connection.execute(
                "INSERT INTO role_permissions (role_id, permission_id, created_at)"
                " VALUES (?, ?, ?)",
                (role_id, permissions[permission], NOW),
            )
        return role_id

    roles = {
        "vault-user": role("vault-user", "global", "vault.read", "vault.add"),
        "ops": role("ops", "global", "vault.read", "workflows.read"),
        "admin": role("admin", "global", "vault.read"),
        "developer": role("developer", "project", "vault.read", "vault.add"),
    }
    connection.execute(
        "INSERT INTO user_roles (user_id, role_id, created_at) VALUES (5, ?, ?)",
        (roles["vault-user"], NOW),
    )
    connection.execute(
        "INSERT INTO user_privileges (user_id, permission_id, created_at) VALUES (5, ?, ?)",
        (permissions["vault.read"], NOW),
    )
    connection.execute(
        "INSERT INTO user_privileges (user_id, permission_id, created_at) VALUES (5, ?, ?)",
        (permissions["workflows.read"], NOW),
    )

    # Two namespaces: one mapped to alpha, one unmapped (Default).
    for number, name in ((1, "old"), (2, "alpha-ns")):
        connection.execute(
            "INSERT INTO vault_namespaces (id, name, owner_user_id, visibility, created_at,"
            " updated_at) VALUES (?, ?, 5, 'shared', ?, ?)",
            (number, name, NOW, NOW),
        )
        connection.execute(
            "INSERT INTO vault_entries (namespace_id, key, value, type, created_at, updated_at)"
            " VALUES (?, 'k', 'encrypted', 'string', ?, ?)",
            (number, NOW, NOW),
        )
    connection.execute(
        "INSERT INTO vault_namespace_projects (namespace_id, project_id) VALUES (2, ?)", (alpha,)
    )
    connection.execute(
        "INSERT INTO vault_namespace_access (namespace_id, user_id, access, created_at)"
        " VALUES (1, 9, 'admin', ?)",
        (NOW,),
    )
    connection.commit()
    return {"alpha": alpha, "default": default, "roles": roles, "permissions": permissions}


def _upgrade(connection) -> None:
    with connection.transaction():
        Migration().upgrade(connection)


def _tables(connection) -> set:
    return {
        row["name"]
        for row in connection.fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def test_namespaces_keep_their_project_and_entries(connection) -> None:
    seeded = _seed(connection)

    _upgrade(connection)

    rows = {
        row["name"]: row
        for row in connection.fetchall("SELECT * FROM vault_namespaces ORDER BY id")
    }
    assert rows["old"]["project_id"] == seeded["default"]
    assert rows["alpha-ns"]["project_id"] == seeded["alpha"]
    # sqlite3.Row: `in` checks values, keys() the column names.
    assert "visibility" not in rows["old"].keys()  # noqa: SIM118
    # Every entry is still there under the same namespace ids.
    assert connection.fetchone("SELECT COUNT(*) AS n FROM vault_entries")["n"] == 2
    assert {row["namespace_id"] for row in connection.fetchall("SELECT * FROM vault_entries")} == {
        1,
        2,
    }


def test_names_become_unique_per_project(connection) -> None:
    seeded = _seed(connection)

    _upgrade(connection)

    connection.execute(
        "INSERT INTO vault_namespaces (project_id, name, created_at, updated_at)"
        " VALUES (?, 'old', ?, ?)",
        (seeded["alpha"], NOW, NOW),
    )
    with pytest.raises(Exception, match="UNIQUE"):
        connection.execute(
            "INSERT INTO vault_namespaces (project_id, name, created_at, updated_at)"
            " VALUES (?, 'old', ?, ?)",
            (seeded["alpha"], NOW, NOW),
        )


def test_old_access_is_removed(connection) -> None:
    seeded = _seed(connection)
    roles, permissions = seeded["roles"], seeded["permissions"]

    _upgrade(connection)

    assert "vault_namespace_access" not in _tables(connection)
    assert "vault_namespace_projects" not in _tables(connection)
    assert connection.fetchone("SELECT 1 FROM roles WHERE name = 'vault-user'") is None
    assert connection.fetchone("SELECT 1 FROM user_roles WHERE user_id = 5") is None

    def granted(role: str) -> set:
        return {
            row["name"]
            for row in connection.fetchall(
                "SELECT p.name FROM role_permissions rp JOIN permissions p"
                " ON p.id = rp.permission_id WHERE rp.role_id = ?",
                (roles[role],),
            )
        }

    # Global custom roles lose Vault permissions only; project roles keep them.
    assert granted("ops") == {"workflows.read"}
    assert granted("developer") == {"vault.read", "vault.add"}
    assert granted("admin") == {"vault.read"}
    # Direct Vault grants go; other direct grants stay.
    assert {
        row["permission_id"]
        for row in connection.fetchall("SELECT permission_id FROM user_privileges")
    } == {permissions["workflows.read"]}


def test_running_again_changes_nothing(connection) -> None:
    _seed(connection)
    _upgrade(connection)
    before = connection.fetchall("SELECT * FROM vault_namespaces ORDER BY id")

    _upgrade(connection)

    assert [
        dict(row) for row in connection.fetchall("SELECT * FROM vault_namespaces ORDER BY id")
    ] == [dict(row) for row in before]
