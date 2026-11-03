"""Open task pages ask "anything new?" often: it must be cheap and never miss a change."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.web.routes import tasks as routes
from lib.database.connection import DatabaseConnection
from lib.tasks.store import TaskStatusError, TaskStore, ensure_tasks_schema, task_version

PROJECT, OTHER = 2, 3


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    ensure_tasks_schema(connection)
    with connection.transaction():
        connection.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT,"
            " email TEXT, is_active INTEGER NOT NULL DEFAULT 1)"
        )
    return connection


@pytest.fixture()
def store(connection) -> TaskStore:
    return TaskStore(connection)


def _task(store: TaskStore, project: int = PROJECT) -> int:
    return store.create(project, "Task", "", "", None, None, "owner")["id"]


def _changes(connection, action) -> int:
    before = task_version(connection, PROJECT)
    action()
    return task_version(connection, PROJECT) - before


def test_a_project_with_no_changes_yet_is_at_zero(connection) -> None:
    assert task_version(connection, PROJECT) == 0


def test_every_change_moves_the_version(connection, store) -> None:
    task = _task(store)
    group = store.create_group(PROJECT, "G", "release", "", None, "owner")
    attachment = store.add_attachment(task, "a.txt", "text/plain", 1, "owner")
    attachment_id = attachment["id"] if isinstance(attachment, dict) else attachment

    for action in (
        lambda: store.create(PROJECT, "Another", "", "", None, None, "owner"),
        lambda: store.update(task, {"title": "New"}, "owner"),
        lambda: store.update(task, {"status": "in_progress"}, "owner"),
        lambda: store.add_comment(task, "owner", "Hello"),
        lambda: store.follow(task, 1, True),
        lambda: store.follow(task, 1, False),
        lambda: store.add_attachment(task, "b.txt", "text/plain", 1, "owner"),
        lambda: store.rename_attachment(attachment_id, "c.txt"),
        lambda: store.delete_attachment(attachment_id),
        lambda: store.create_group(PROJECT, "G2", "release", "", None, "owner"),
        lambda: store.update_group(group["id"], {"name": "G3"}),
        lambda: store.add_to_group(group["id"], [task]),
        lambda: store.delete_group(group["id"]),
        lambda: store.update_settings(PROJECT, "NEW", None),
        lambda: store.add_types(PROJECT, ["custom"]),
        lambda: store.delete(task),
    ):
        # At least once: some changes are made of others, and one more reload is harmless.
        assert _changes(connection, action) >= 1


def test_another_project_does_not_cause_a_reload_here(connection, store) -> None:
    task = _task(store, OTHER)

    assert _changes(connection, lambda: store.update(task, {"title": "New"}, "owner")) == 0
    assert task_version(connection, OTHER) > 0


def test_a_refused_change_does_not_cause_a_reload(connection, store) -> None:
    task = _task(store)
    store.update(task, {"status": "done"}, "owner")
    before = task_version(connection, PROJECT)

    with pytest.raises(TaskStatusError):  # a closed task is only reopened
        store.update(task, {"status": "in_progress"}, "owner")

    assert task_version(connection, PROJECT) == before


def test_background_bookkeeping_does_not_cause_a_reload(connection, store) -> None:
    task = _task(store)

    assert _changes(connection, lambda: store.mark_reminder_sent(task)) == 0
    assert _changes(connection, lambda: store.mark_due_alert(task, "x")) == 0
    assert _changes(connection, lambda: store.due_alerts(date(2026, 1, 1))) == 0


def test_version_survives_a_new_store(connection, store) -> None:
    _task(store)
    before = task_version(connection, PROJECT)

    assert task_version(connection, PROJECT) == before
    TaskStore(connection)
    assert task_version(connection, PROJECT) == before


def test_asking_for_the_version_changes_nothing_and_stays_small(connection, monkeypatch) -> None:
    # An open page asks every few seconds: this must not build a store or run its set-up.
    monkeypatch.setattr(
        routes,
        "_store",
        lambda request: pytest.fail("the version check must not build a TaskStore"),
    )
    monkeypatch.setattr(routes, "_project_id", lambda request, user, permission: PROJECT)
    context = SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))
    response = SimpleNamespace(headers={})

    result = routes.tasks_version(request, response, ("t", MagicMock(), MagicMock()))

    assert result == {"version": 0}
    assert response.headers["Cache-Control"] == "no-store"
    assert task_version(connection, PROJECT) == 0


def test_the_version_check_needs_read_permission(connection, monkeypatch) -> None:
    asked = []

    def project_id(request, user, permission):
        asked.append(permission)
        return PROJECT

    monkeypatch.setattr(routes, "_project_id", project_id)
    context = SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))

    routes.tasks_version(request, SimpleNamespace(headers={}), ("t", MagicMock(), MagicMock()))

    assert asked == ["tasks.read"]
