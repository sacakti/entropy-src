"""Starting on an up-to-date database must stay cheap: on a server across a network,
every statement is a round trip, and a long write holds the shared connection."""

from __future__ import annotations

import re

from test_permission_model import connection  # noqa: F401

from lib.authorization.constants import PERMISSIONS
from lib.authorization.initializer import AuthorizationInitializer


def _traced(connection, action):  # noqa: F811
    statements = []
    connection.connection.set_trace_callback(statements.append)
    action()
    connection.connection.set_trace_callback(None)
    return statements


WRITES = re.compile(r"^\s*(INSERT|UPDATE|DELETE|REPLACE)\b", re.IGNORECASE)


def test_reconciling_an_up_to_date_database_writes_nothing(connection) -> None:  # noqa: F811
    AuthorizationInitializer(connection).reconcile()
    statements = _traced(connection, AuthorizationInitializer(connection).reconcile)
    assert [s for s in statements if WRITES.match(s)] == []
    assert len(statements) < len(PERMISSIONS)


def test_a_new_permission_and_a_changed_one_are_still_applied(connection) -> None:  # noqa: F811
    AuthorizationInitializer(connection).reconcile()
    first, second = PERMISSIONS[0].name, PERMISSIONS[1].name
    connection.execute("DELETE FROM permissions WHERE name = ?", (first,))
    connection.execute("UPDATE permissions SET description = 'old' WHERE name = ?", (second,))
    connection.commit()

    AuthorizationInitializer(connection).reconcile()

    assert connection.fetchone("SELECT 1 FROM permissions WHERE name = ?", (first,))
    row = connection.fetchone("SELECT description FROM permissions WHERE name = ?", (second,))
    assert row["description"] == PERMISSIONS[1].description


def test_builtin_roles_are_put_back_as_defined(connection) -> None:  # noqa: F811
    AuthorizationInitializer(connection).reconcile()
    connection.execute("UPDATE roles SET title = 'edited' WHERE builtin = 1")
    name = connection.fetchone("SELECT name FROM roles WHERE builtin = 1 ORDER BY name")["name"]
    connection.execute(
        "DELETE FROM role_permissions WHERE role_id = (SELECT id FROM roles WHERE name = ?)",
        (name,),
    )
    connection.commit()

    AuthorizationInitializer(connection).reconcile()

    titles = {
        row["title"] for row in connection.fetchall("SELECT title FROM roles WHERE builtin = 1")
    }
    assert "edited" not in titles
    restored = connection.fetchone(
        "SELECT count(*) AS n FROM role_permissions rp JOIN roles r ON r.id = rp.role_id"
        " WHERE r.name = ?",
        (name,),
    )
    assert restored["n"] > 0
