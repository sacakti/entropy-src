"""A membership of a deleted user must not break assigning tasks."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core.web.routes import admin as admin_routes
from core.web.routes.tasks import _validate_assignee
from lib.authorization.projects import Projects, ensure_projects_schema
from lib.database.connection import DatabaseConnection

Migration = importlib.import_module(
    "lib.migrations.scripts.030_project_member_orphans"
).ProjectMemberOrphansMigration

PROJECT = 2
ACTOR = SimpleNamespace(username="actor", id=99)
DIRECT, IN_GROUP, OUTSIDER, INACTIVE, DELETED = 1, 2, 3, 4, 50
TEAM, DELETED_TEAM = 1, 60
ROLE = 7


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    with connection.transaction():
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,"
            " email TEXT, is_active INTEGER NOT NULL DEFAULT 1)"
        )
        connection.execute("CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("CREATE TABLE user_groups (user_id INTEGER, group_id INTEGER)")
        connection.execute("CREATE TABLE user_roles (user_id INTEGER, role_id INTEGER)")
        connection.execute("CREATE TABLE group_roles (group_id INTEGER, role_id INTEGER)")
        connection.execute(
            "CREATE TABLE roles (id INTEGER PRIMARY KEY, name TEXT, title TEXT, scope TEXT)"
        )
        connection.execute(
            "CREATE TABLE project_members (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " project_id INTEGER, user_id INTEGER, group_id INTEGER, role_id INTEGER,"
            " created_at TEXT)"
        )
        connection.execute(
            "INSERT INTO roles VALUES (?, 'operator', 'Operator', 'project')", (ROLE,)
        )
        for user_id, name, active in (
            (DIRECT, "direct", 1),
            (IN_GROUP, "ingroup", 1),
            (OUTSIDER, "outsider", 1),
            (INACTIVE, "gone", 0),
        ):
            connection.execute(
                "INSERT INTO users (id, username, is_active) VALUES (?, ?, ?)",
                (user_id, name, active),
            )
        connection.execute("INSERT INTO groups VALUES (?, 'team')", (TEAM,))
        connection.execute("INSERT INTO user_groups VALUES (?, ?)", (IN_GROUP, TEAM))
        for column, value in (
            ("user_id", DIRECT),
            ("user_id", INACTIVE),
            ("group_id", TEAM),
            # What deleting a user or group used to leave behind.
            ("user_id", DELETED),
            ("group_id", DELETED_TEAM),
        ):
            connection.execute(
                f"INSERT INTO project_members (project_id, {column}, role_id) VALUES (?, ?, ?)",
                (PROJECT, value, ROLE),
            )
    return connection


def _request(connection) -> SimpleNamespace:
    # Direct and group members may read the project's tasks; the deleted never appear.
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        authorization=SimpleNamespace(
            has_permission=lambda user_id, name, project: user_id in (DIRECT, IN_GROUP, INACTIVE)
        ),
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))


def _count(connection, where: str = "1 = 1") -> int:
    return connection.fetchone(f"SELECT COUNT(*) AS n FROM project_members WHERE {where}")["n"]


# ----------------------------------------------------------------------
# The crash
# ----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["direct", "DIRECT", "ingroup"])
def test_members_can_be_assigned_despite_a_deleted_member(connection, name) -> None:
    _validate_assignee(_request(connection), ACTOR, PROJECT, name)


@pytest.mark.parametrize("name", ["outsider", "nobody", "gone"])
def test_others_are_refused_rather_than_crashing(connection, name) -> None:
    with pytest.raises(HTTPException) as caught:
        _validate_assignee(_request(connection), ACTOR, PROJECT, name)

    assert caught.value.status_code == 422


@pytest.mark.parametrize("name", [None, "", "actor", "ACTOR"])
def test_no_assignee_or_oneself_is_always_allowed(connection, name) -> None:
    _validate_assignee(_request(connection), ACTOR, PROJECT, name)


def test_project_members_leave_out_those_that_no_longer_exist(connection, monkeypatch) -> None:
    monkeypatch.setattr("lib.authorization.projects.ensure_projects_schema", lambda c: None)

    members = Projects.members(SimpleNamespace(connection=connection), PROJECT)

    assert {(item["kind"], item["name"]) for item in members} == {
        ("user", "direct"),
        ("user", "gone"),
        ("group", "team"),
    }


# ----------------------------------------------------------------------
# Where they came from
# ----------------------------------------------------------------------


def _context(connection, deleted) -> SimpleNamespace:
    manager = SimpleNamespace(get=lambda name: deleted, delete=MagicMock())
    return SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        user_manager=manager,
        group_manager=manager,
    )


def test_deleting_a_user_removes_their_memberships(connection, monkeypatch) -> None:
    context = _context(connection, SimpleNamespace(id=DIRECT))
    monkeypatch.setattr(admin_routes, "_context", lambda request: context)
    monkeypatch.setattr(admin_routes, "_require", lambda *arguments: ACTOR)
    monkeypatch.setattr(admin_routes, "NotificationRepository", MagicMock())

    admin_routes.delete_user("direct", MagicMock(), MagicMock())

    assert _count(connection, f"user_id = {DIRECT}") == 0
    assert _count(connection, f"user_id = {INACTIVE}") == 1


def test_deleting_a_group_removes_its_memberships(connection, monkeypatch) -> None:
    context = _context(connection, SimpleNamespace(id=TEAM))
    monkeypatch.setattr(admin_routes, "_context", lambda request: context)
    monkeypatch.setattr(admin_routes, "_require", lambda *arguments: ACTOR)

    admin_routes.delete_group("team", MagicMock(), MagicMock())

    assert _count(connection, f"group_id = {TEAM}") == 0
    assert _count(connection, f"user_id = {DIRECT}") == 1


# ----------------------------------------------------------------------
# Migration 030
# ----------------------------------------------------------------------


def test_migration_removes_only_memberships_of_what_is_gone(connection) -> None:
    with connection.transaction():
        Migration().upgrade(connection)

    assert _count(connection) == 3
    assert _count(connection, f"user_id = {DELETED}") == 0
    assert _count(connection, f"group_id = {DELETED_TEAM}") == 0
    assert _count(connection, f"user_id = {DIRECT}") == 1
    assert _count(connection, f"user_id = {INACTIVE}") == 1
    assert _count(connection, f"group_id = {TEAM}") == 1


def test_migration_runs_again_and_tolerates_missing_tables(connection, tmp_path) -> None:
    with connection.transaction():
        Migration().upgrade(connection)
        Migration().upgrade(connection)

    assert _count(connection) == 3

    empty = DatabaseConnection(tmp_path / "empty.db")
    with empty.transaction():
        Migration().upgrade(empty)


def test_a_new_database_has_the_table_the_migration_expects(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.authorization.initializer.AuthorizationInitializer.reconcile", lambda self: None
    )
    connection = DatabaseConnection(tmp_path / "new.db")
    with connection.transaction():
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE groups (id INTEGER PRIMARY KEY)")
        ensure_projects_schema(connection)
        Migration().upgrade(connection)

    assert _count(connection) == 0
