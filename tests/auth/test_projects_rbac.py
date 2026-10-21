"""Projects and scoped roles."""

from __future__ import annotations

import pytest

from lib.authorization.initializer import AuthorizationInitializer
from lib.authorization.projects import Projects, default_project_id, role_scope
from lib.authorization.service import AuthorizationService

from test_permission_model import _grant_role, _role_permissions, _user, connection  # noqa: F401


def _project(connection, key: str) -> int:  # noqa: F811
    return Projects(connection).create(key, key.title(), "", "admin")["id"]


def test_builtin_roles_have_scopes(connection) -> None:  # noqa: F811
    AuthorizationInitializer(connection).reconcile()

    scopes = {
        row["name"]: row["scope"]
        for row in connection.fetchall("SELECT name, scope FROM roles WHERE builtin = 1")
    }
    assert scopes["viewer"] == scopes["maintainer"] == "project"
    assert scopes["admin"] == scopes["node-admin"] == "global"
    assert _role_permissions(connection, "viewer") == {
        "workflows.read",
        "schedules.list",
        "plugins.read",
    }
    assert "workflows.delete" in _role_permissions(connection, "maintainer")
    # The generated per-module type roles are gone.
    assert connection.fetchone("SELECT 1 FROM roles WHERE name = 'workflows-read'") is None


def test_project_roles_apply_to_their_project_only(connection) -> None:  # noqa: F811
    AuthorizationInitializer(connection).reconcile()
    projects = Projects(connection)
    payments = _project(connection, "payments")
    billing = _project(connection, "billing")
    alice = _user(connection, "alice")
    projects.set_members(payments, [{"kind": "user", "name": "alice", "role": "developer"}])
    projects.set_members(billing, [{"kind": "user", "name": "alice", "role": "viewer"}])
    service = AuthorizationService(connection)

    assert service.has_permission(alice, "workflows.write", payments)
    assert not service.has_permission(alice, "workflows.write", billing)
    assert service.has_permission(alice, "workflows.read", billing)
    # In some project: enough to offer "Create workflow".
    assert service.has_permission(alice, "workflows.write")
    assert service.projects_with(alice, "workflows.write") == {payments}
    assert service.projects_with(alice, "workflows.read") == {payments, billing}
    assert "workflows.write" not in service.permissions(alice, billing)
    assert not service.has_permission(alice, "nodes.manage")


def test_group_membership_and_global_roles(connection) -> None:  # noqa: F811
    AuthorizationInitializer(connection).reconcile()
    projects = Projects(connection)
    ops = _project(connection, "ops")
    bob = _user(connection, "bob")
    connection.execute(
        "INSERT INTO groups (name, description, created_at, updated_at)"
        " VALUES ('oncall', '', 'x', 'x')"
    )
    connection.execute(
        "INSERT INTO user_groups (user_id, group_id, created_at)"
        " SELECT ?, id, 'x' FROM groups WHERE name = 'oncall'",
        (bob,),
    )
    connection.commit()
    projects.set_members(ops, [{"kind": "group", "name": "oncall", "role": "operator"}])
    service = AuthorizationService(connection)

    assert service.has_permission(bob, "workflows.execute", ops)
    assert not service.has_permission(bob, "workflows.write", ops)

    _grant_role(connection, bob, "admin")
    assert service.projects_with(bob, "workflows.write") is None  # every project


def test_global_roles_cannot_be_given_in_a_project(connection) -> None:  # noqa: F811
    AuthorizationInitializer(connection).reconcile()
    projects = Projects(connection)
    _user(connection, "carol")

    with pytest.raises(ValueError, match="global role"):
        projects.set_members(
            default_project_id(connection), [{"kind": "user", "name": "carol", "role": "admin"}]
        )


def test_old_roles_and_direct_grants_are_converted(connection) -> None:  # noqa: F811
    # An older database: generated type roles, one in use, and a direct grant.
    connection.execute(
        "INSERT INTO modules (name, description) VALUES ('workflows', 'w'), ('nodes', 'n')"
    )
    connection.execute(
        "INSERT INTO permissions (module_id, name, description, permission_type)"
        " SELECT id, 'workflows.read', 'r', 'read' FROM modules WHERE name = 'workflows'"
    )
    connection.execute(
        "INSERT INTO permissions (module_id, name, description, permission_type)"
        " SELECT id, 'nodes.list', 'l', 'read' FROM modules WHERE name = 'nodes'"
    )
    for name in ("workflows-read", "nodes-read", "read"):
        connection.execute(
            "INSERT INTO roles (name, description, created_at, updated_at) VALUES (?, '', 'x', 'x')",
            (name,),
        )
    connection.execute(
        "INSERT INTO role_permissions (role_id, permission_id, created_at)"
        " SELECT r.id, p.id, 'x' FROM roles r, permissions p"
        " WHERE r.name = 'workflows-read' AND p.name = 'workflows.read'"
    )
    connection.commit()
    reader = _user(connection, "reader")
    _grant_role(connection, reader, "workflows-read")
    viewer = _user(connection, "viewer")
    connection.execute(
        "INSERT INTO user_privileges (user_id, permission_id, created_at)"
        " SELECT ?, id, 'x' FROM permissions WHERE name = 'nodes.list'",
        (viewer,),
    )
    connection.commit()

    AuthorizationInitializer(connection).reconcile()
    service = AuthorizationService(connection)
    default = default_project_id(connection)

    # Used project-type role: kept as a custom role, now held in the Default project.
    assert service.has_permission(reader, "workflows.read", default)
    assert tuple(
        connection.fetchone("SELECT scope, builtin FROM roles WHERE name = 'workflows-read'")
    ) == ("project", 0)
    # Unused generated roles are removed.
    assert connection.fetchone("SELECT 1 FROM roles WHERE name = 'nodes-read'") is None
    # A direct grant becomes the user's own global role.
    assert service.has_permission(viewer, "nodes.list")
    assert connection.fetchone("SELECT COUNT(*) FROM user_privileges")[0] == 0

    # Converting again changes nothing.
    AuthorizationInitializer(connection).reconcile()
    assert service.has_permission(reader, "workflows.read", default)


def test_role_scope() -> None:
    assert role_scope(["workflows.read", "schedules.list"]) == "project"
    assert role_scope(["workflows.read", "nodes.manage"]) == "global"
    assert role_scope([]) == "global"


def test_nodes_shared_or_assigned(connection) -> None:  # noqa: F811
    AuthorizationInitializer(connection).reconcile()
    connection.execute(
        "CREATE TABLE IF NOT EXISTS nodes (id INTEGER PRIMARY KEY, name TEXT UNIQUE,"
        " scope TEXT NOT NULL DEFAULT 'shared')"
    )
    connection.execute("INSERT INTO nodes (name) VALUES ('edge')")
    connection.commit()
    projects = Projects(connection)
    payments = _project(connection, "payments")
    billing = _project(connection, "billing")

    assert projects.node_available("edge", billing)
    projects.set_node_access("edge", "assigned", [payments])
    assert projects.node_available("edge", payments)
    assert not projects.node_available("edge", billing)
