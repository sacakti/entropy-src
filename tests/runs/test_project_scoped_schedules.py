"""Schedule names are unique per project: store, migration 027 and transfers."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from core.web.transfer import ProjectTransfer
from lib.authorization.projects import default_project_id
from lib.database.connection import DatabaseConnection
from lib.database.objects.events import WorkflowEventsTable
from lib.database.objects.jobs import WorkflowJobsTable
from lib.runs.schedules import ScheduleError, ScheduleStore

Migration = importlib.import_module(
    "lib.migrations.scripts.027_project_scoped_schedules"
).ProjectScopedSchedulesMigration

NOW = "2026-01-01T00:00:00"


@pytest.fixture
def connection(tmp_path: Path, monkeypatch) -> DatabaseConnection:
    # Permission seeding needs the authorization tables; not under test here.
    monkeypatch.setattr(
        "lib.authorization.initializer.AuthorizationInitializer.reconcile",
        lambda self: None,
    )
    connection = DatabaseConnection(tmp_path / "entropy.db")
    WorkflowJobsTable().create(connection)
    WorkflowEventsTable().create(connection)
    return connection


def _spec(name: str = "Nightly", **extra: Any) -> Dict[str, Any]:
    return {"name": name, "kind": "plugin", "target": "a/b", "cron": "0 2 * * *", **extra}


def _second_project(connection: DatabaseConnection) -> int:
    default_project_id(connection)
    with connection.transaction():
        cursor = connection.execute(
            "INSERT INTO projects (key, name, description, created_by, created_at, updated_at)"
            " VALUES ('other', 'Other', '', NULL, ?, ?)",
            (NOW, NOW),
        )
    return int(cursor.lastrowid)


def _transfer(connection: DatabaseConnection) -> ProjectTransfer:
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection), workflow_manager=None
    )
    return ProjectTransfer(context)


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


def test_the_same_name_exists_in_two_projects(connection) -> None:
    store = ScheduleStore(connection)
    other = _second_project(connection)

    first = store.create(_spec(), 1, "admin", project_id=default_project_id(connection))
    second = store.create(_spec(), 1, "admin", project_id=other)

    assert first["id"] != second["id"]
    assert [item["id"] for item in store.list(other)] == [second["id"]]


def test_a_name_is_still_unique_within_a_project_ignoring_case(connection) -> None:
    store = ScheduleStore(connection)
    other = _second_project(connection)
    store.create(_spec(), 1, "admin", project_id=other)

    with pytest.raises(ScheduleError) as caught:
        store.create(_spec("NIGHTLY"), 1, "admin", project_id=other)
    assert caught.value.status == 409


def test_renaming_only_collides_within_the_project(connection) -> None:
    store = ScheduleStore(connection)
    other = _second_project(connection)
    store.create(_spec("Taken"), 1, "admin", project_id=default_project_id(connection))
    schedule = store.create(_spec(), 1, "admin", project_id=other)

    assert store.update(schedule["id"], {"name": "Taken"})["name"] == "Taken"

    sibling = store.create(_spec("Sibling"), 1, "admin", project_id=other)
    with pytest.raises(ScheduleError):
        store.update(sibling["id"], {"name": "taken"})
    # Saving a schedule under its own name is not a collision.
    assert store.update(sibling["id"], {"name": "Sibling"})["name"] == "Sibling"


def test_a_schedule_without_a_project_belongs_to_default(connection) -> None:
    store = ScheduleStore(connection)
    schedule = store.create(_spec(), 1, "admin")

    assert schedule["project_id"] == default_project_id(connection)
    with pytest.raises(ScheduleError):
        store.create(_spec(), 1, "admin", project_id=default_project_id(connection))


# ----------------------------------------------------------------------
# Migration 027
# ----------------------------------------------------------------------


def _legacy_schedules(connection: DatabaseConnection, *, project_column: bool = True) -> None:
    """The table as it was before migration 027."""

    project = ", project_id INTEGER" if project_column else ""
    connection.execute(f"""
        CREATE TABLE schedules
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL CHECK (kind IN ('workflow', 'plugin')),
            target TEXT NOT NULL,
            cron TEXT NOT NULL,
            timezone TEXT NOT NULL DEFAULT 'UTC',
            node TEXT NOT NULL DEFAULT 'local',
            parameters TEXT NOT NULL DEFAULT '{{}}',
            enabled INTEGER NOT NULL DEFAULT 1,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            next_run_at TEXT,
            last_run_at TEXT
            {project}
        )
        """)


def _legacy_row(connection: DatabaseConnection, row_id: int, name: str, **columns: Any) -> None:
    extra = "".join(f", {column}" for column in columns)
    marks = "".join(", ?" for _ in columns)
    connection.execute(
        "INSERT INTO schedules (id, name, kind, target, cron, user_id, username,"
        f" created_at, updated_at, last_run_at{extra})"
        f" VALUES (?, ?, 'plugin', 'a/b', '0 2 * * *', 1, 'admin', ?, ?, ?{marks})",
        (row_id, name, NOW, NOW, NOW, *columns.values()),
    )


def test_migration_keeps_ids_and_projects_and_frees_the_name(connection) -> None:
    other = _second_project(connection)
    default = default_project_id(connection)
    _legacy_schedules(connection)
    _legacy_row(connection, 7, "Old")
    _legacy_row(connection, 9, "Owned", project_id=other)
    connection.commit()

    with connection.transaction():
        Migration().upgrade(connection)

    rows = {row["id"]: row for row in connection.fetchall("SELECT * FROM schedules")}
    assert {key: row["project_id"] for key, row in rows.items()} == {7: default, 9: other}
    assert rows[9]["last_run_at"] == NOW

    # Both directions of the new constraint hold on the migrated table.
    with connection.transaction():
        _legacy_row(connection, 10, "Owned", project_id=default)
    with pytest.raises(Exception, match="UNIQUE"), connection.transaction():
        _legacy_row(connection, 11, "Owned", project_id=other)


def test_migration_handles_a_table_without_the_project_column(connection) -> None:
    default = default_project_id(connection)
    _legacy_schedules(connection, project_column=False)
    _legacy_row(connection, 1, "Old")
    connection.commit()

    with connection.transaction():
        Migration().upgrade(connection)

    assert connection.fetchone("SELECT project_id FROM schedules")["project_id"] == default


def test_migration_runs_once_and_skips_a_new_install(connection) -> None:
    store = ScheduleStore(connection)  # creates the current table
    schedule = store.create(_spec(), 1, "admin")

    with connection.transaction():
        Migration().upgrade(connection)
        Migration().upgrade(connection)

    assert store.get(schedule["id"])["name"] == "Nightly"


def test_migration_skips_a_database_without_schedules(connection) -> None:
    with connection.transaction():
        Migration().upgrade(connection)

    assert connection.fetchone("SELECT 1 FROM sqlite_master WHERE name = 'schedules'") is None


# ----------------------------------------------------------------------
# Move and copy between projects
# ----------------------------------------------------------------------


USER = SimpleNamespace(id=1, username="admin")


def _transfer_schedule(connection, schedule_id: int, source: int, target: int, mode: str):
    return _transfer(connection).transfer(
        source,
        target,
        workflows=[],
        schedule_ids=[schedule_id],
        mode=mode,
        with_schedules=False,
        user=USER,
    )


def test_moving_onto_a_taken_name_is_reported_and_leaves_the_schedule(connection) -> None:
    store = ScheduleStore(connection)
    other = _second_project(connection)
    default = default_project_id(connection)
    schedule = store.create(_spec(), 1, "admin", project_id=default)
    store.create(_spec("NIGHTLY"), 1, "admin", project_id=other)

    result = _transfer_schedule(connection, schedule["id"], default, other, "move")

    assert result["schedules"] == []
    assert "already has one of that name" in result["errors"][0]
    assert store.get(schedule["id"])["project_id"] == default


def test_moving_to_a_free_name_keeps_it(connection) -> None:
    store = ScheduleStore(connection)
    other = _second_project(connection)
    default = default_project_id(connection)
    schedule = store.create(_spec(), 1, "admin", project_id=default)

    result = _transfer_schedule(connection, schedule["id"], default, other, "move")

    assert result["errors"] == []
    assert store.get(schedule["id"])["project_id"] == other


def test_copying_keeps_the_name_unless_the_target_uses_it(connection) -> None:
    store = ScheduleStore(connection)
    other = _second_project(connection)
    default = default_project_id(connection)
    schedule = store.create(_spec(), 1, "admin", project_id=default)

    first = _transfer_schedule(connection, schedule["id"], default, other, "copy")
    second = _transfer_schedule(connection, schedule["id"], default, other, "copy")

    assert first["schedules"] == [{"name": "Nightly", "as": "Nightly"}]
    assert second["schedules"] == [{"name": "Nightly", "as": "Nightly-2"}]
