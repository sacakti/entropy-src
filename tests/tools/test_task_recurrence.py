"""Repeating tasks and reminders."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from core.web.routes import tasks as routes
from lib.database.connection import DatabaseConnection
from lib.runs.background import RunsBackground
from lib.tasks.recurrence import next_date, next_moment
from lib.tasks.store import TaskStore, ensure_tasks_schema

PROJECT = 2
OWNER, WATCHER = 1, 2
RECORD = ("token", MagicMock(), SimpleNamespace(id=OWNER, username="owner"))


@pytest.mark.parametrize(
    ("start", "rule", "expected"),
    [
        ("2026-11-03", "daily", "2026-11-04"),
        ("2026-11-02", "weekly", "2026-11-09"),
        ("2026-11-05", "weekdays", "2026-11-06"),  # Thursday to Friday
        ("2026-11-06", "weekdays", "2026-11-09"),  # Friday to Monday
        ("2026-11-07", "weekdays", "2026-11-09"),  # Saturday to Monday
        ("2026-11-15", "monthly", "2026-12-15"),
        ("2026-12-15", "monthly", "2027-01-15"),  # over the year's end
        ("2027-01-31", "monthly", "2027-02-28"),  # a shorter month
        ("2028-01-31", "monthly", "2028-02-29"),  # a leap year
        ("2026-05-20", "yearly", "2027-05-20"),
        ("2028-02-29", "yearly", "2029-02-28"),
    ],
)
def test_the_next_date(start, rule, expected) -> None:
    today = date.fromisoformat(start)

    assert next_date(date.fromisoformat(start), rule, today).isoformat() == expected


def test_occurrences_already_past_are_skipped() -> None:
    upcoming = next_date(date(2026, 1, 5), "weekly", date(2026, 3, 1))

    # Keeps its rhythm (a Monday), and is the first one still ahead.
    assert upcoming == date(2026, 3, 2) and upcoming.weekday() == 0


def test_the_next_moment_keeps_the_time_of_day_and_is_ahead() -> None:
    current = datetime(2026, 1, 5, 6, 30, tzinfo=timezone.utc)
    now = datetime(2026, 1, 8, 12, 0, tzinfo=timezone.utc)

    assert next_moment(current, "daily", now) == datetime(2026, 1, 9, 6, 30, tzinfo=timezone.utc)


def test_an_unknown_rule_is_an_error() -> None:
    with pytest.raises(ValueError):
        next_date(date(2026, 1, 1), "sometimes", date(2026, 1, 1))


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    ensure_tasks_schema(connection)
    with connection.transaction():
        connection.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT,"
            " full_name TEXT, email TEXT, is_active INTEGER NOT NULL DEFAULT 1)"
        )
        connection.execute("INSERT INTO users (id, username) VALUES (?, 'owner')", (OWNER,))
        connection.execute("INSERT INTO users (id, username) VALUES (?, 'wes')", (WATCHER,))
    return connection


@pytest.fixture()
def store(connection) -> TaskStore:
    return TaskStore(connection)


def _repeating(store: TaskStore, **values) -> dict:
    defaults = dict(due_date="2026-11-02", due_repeat="weekly", due_time="14:30")
    return store.create(
        PROJECT, "Backup", "Run it", "Note", "wes", None, "owner", **{**defaults, **values}
    )


def test_closing_makes_the_next_occurrence_of_the_same_work(store) -> None:
    group = store.create_group(PROJECT, "Ops", "release", "", None, "owner")
    task = _repeating(store, group_ids=[group["id"]], severity="high", type="task")
    store.follow(task["id"], WATCHER, True)

    upcoming = store.create_next_occurrence(task["id"], date(2026, 11, 2), "owner")

    assert upcoming["id"] != task["id"] and upcoming["key"] != task["key"]
    assert upcoming["due_date"] == "2026-11-09" and upcoming["due_time"] == "14:30"
    assert upcoming["due_repeat"] == "weekly" and upcoming["status"] == "todo"
    assert (upcoming["title"], upcoming["description"], upcoming["remarks"]) == (
        "Backup",
        "Run it",
        "Note",
    )
    assert (upcoming["assignee"], upcoming["severity"], upcoming["type"]) == ("wes", "high", "task")
    assert upcoming["group_ids"] == [group["id"]] and upcoming["follower_ids"] == [WATCHER]
    assert upcoming["comments"] == []


def test_closing_again_makes_no_second_one(store) -> None:
    task = _repeating(store)

    assert store.create_next_occurrence(task["id"], date(2026, 11, 2), "owner")
    assert store.create_next_occurrence(task["id"], date(2026, 11, 2), "owner") is None


def test_a_task_that_does_not_repeat_makes_none(store) -> None:
    task = store.create(PROJECT, "Once", "", "", None, None, "owner", due_date="2026-11-02")

    assert store.create_next_occurrence(task["id"], date(2026, 11, 2), "owner") is None


def test_a_reminder_moves_with_the_next_occurrence(store) -> None:
    task = _repeating(store, reminder_repeat=None)
    store.update(task["id"], {"reminder_at": "2026-11-01T09:00:00+00:00"})

    upcoming = store.create_next_occurrence(task["id"], date(2026, 11, 2), "owner")

    assert upcoming["reminder_at"].startswith("2026-11-08T09:00:00")


# ----------------------------------------------------------------------
# The routes
# ----------------------------------------------------------------------


@pytest.fixture()
def world(connection, store, monkeypatch) -> SimpleNamespace:
    sent = []
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        authorization=SimpleNamespace(has_permission=lambda *arguments: True),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))
    monkeypatch.setattr(
        "lib.database.repositories.notifications.notify_user",
        lambda context, user_id, title, message="", level="info", source=None: sent.append(
            {"user": user_id, "title": title, "message": message, "source": source}
        ),
    )
    monkeypatch.setattr(routes, "current_project", lambda request, user: {"id": PROJECT})
    monkeypatch.setattr(routes, "require", lambda *arguments: None)
    return SimpleNamespace(request=request, store=store, sent=sent)


def _create(world, **values) -> dict:
    return routes.create_task(routes.TaskCreate(title="T", **values), world.request, RECORD)


def _update(world, task, **values) -> dict:
    return routes.update_task(
        task["id"], routes.TaskUpdate(**values), world.request, BackgroundTasks(), RECORD
    )


def test_creating_keeps_time_and_repeats(world) -> None:
    task = _create(
        world,
        due_date="2030-01-01",
        due_time="09:30",
        due_repeat="monthly",
        reminder_at="2029-12-31T09:00:00Z",
        reminder_repeat="daily",
    )

    assert (task["due_time"], task["due_repeat"], task["reminder_repeat"]) == (
        "09:30",
        "monthly",
        "daily",
    )


@pytest.mark.parametrize(
    "values",
    [
        {"due_time": "09:00"},
        {"due_repeat": "weekly"},
        {"reminder_repeat": "daily"},
        {"due_date": "2030-01-01", "due_time": "25:00"},
        {"due_date": "2030-01-01", "due_time": "9am"},
        {"due_date": "2030-01-01", "due_repeat": "sometimes"},
        {"reminder_at": "2030-01-01T09:00:00Z", "reminder_repeat": "sometimes"},
    ],
)
def test_a_repeat_or_time_needs_something_valid_to_belong_to(world, values) -> None:
    with pytest.raises(HTTPException) as caught:
        _create(world, **values)

    assert caught.value.status_code == 422


def test_removing_the_date_removes_its_time_and_repeat(world) -> None:
    task = _create(world, due_date="2030-01-01", due_time="09:30", due_repeat="weekly")

    updated = _update(world, task, due_date=None)

    assert (updated["due_date"], updated["due_time"], updated["due_repeat"]) == (None, None, None)


def test_removing_the_reminder_removes_its_repeat(world) -> None:
    task = _create(world, reminder_at="2030-01-01T09:00:00Z", reminder_repeat="weekly")

    updated = _update(world, task, reminder_at=None)

    assert updated["reminder_at"] is None and updated["reminder_repeat"] is None


def test_changing_the_schedule_is_told_to_watchers(world) -> None:
    task = _create(world, due_date="2030-01-01")
    world.store.follow(task["id"], WATCHER, True)

    _update(world, task, due_time="10:00", due_repeat="weekly")

    [alert] = world.sent
    assert "due time from none to 10:00" in alert["message"]
    assert "repeat from none to weekly" in alert["message"]


def test_closing_through_the_route_makes_and_announces_the_next_one(world) -> None:
    task = _create(world, due_date="2030-01-07", due_repeat="weekly")
    world.store.follow(task["id"], WATCHER, True)
    world.sent.clear()

    _update(world, task, status="done")

    items = world.store.list(PROJECT)
    assert len(items) == 2
    upcoming = next(item for item in items if item["id"] != task["id"])
    assert upcoming["due_date"] == "2030-01-14"
    assert any(
        item["title"].startswith("Next occurrence:") and item["source"] == f"task:{upcoming['id']}"
        for item in world.sent
    )


def test_other_status_changes_make_no_next_one(world) -> None:
    task = _create(world, due_date="2030-01-07", due_repeat="weekly")

    _update(world, task, status="in_progress")

    assert len(world.store.list(PROJECT)) == 1


# ----------------------------------------------------------------------
# Reminders going out
# ----------------------------------------------------------------------


@pytest.fixture()
def background(connection, monkeypatch) -> SimpleNamespace:
    sent = []
    monkeypatch.setattr(
        "lib.system.settings.settings_for",
        lambda context: SimpleNamespace(values=lambda name: {"enabled": False}),
    )
    instance = SimpleNamespace(
        _context=None,
        _connection=connection,
        _notify=lambda user_id, title, message, level, source="": sent.append((user_id, title)),
    )
    return SimpleNamespace(instance=instance, sent=sent)


def test_a_repeating_reminder_fires_and_comes_round_again(background, store) -> None:
    task = store.create(
        PROJECT, "T", "", "", "wes", "2020-01-01T09:00:00+00:00", "owner", reminder_repeat="daily"
    )

    RunsBackground.send_task_reminders(background.instance)

    after = store.get(task["id"])
    assert len(background.sent) == 1
    assert after["reminder_sent"] == 0
    assert datetime.fromisoformat(after["reminder_at"]) > datetime.now(timezone.utc)
    assert after["reminder_at"][11:16] == "09:00"

    # Next time it is not due yet, so it does not fire again.
    RunsBackground.send_task_reminders(background.instance)
    assert len(background.sent) == 1


def test_a_repeating_reminder_of_a_closed_task_stops(background, store) -> None:
    task = store.create(
        PROJECT,
        "T",
        "",
        "",
        "wes",
        "2020-01-01T09:00:00+00:00",
        "owner",
        reminder_repeat="daily",
        status="done",
    )

    RunsBackground.send_task_reminders(background.instance)

    assert background.sent == []
    assert store.get(task["id"])["reminder_sent"] == 1


def test_a_plain_reminder_fires_once(background, store) -> None:
    store.create(PROJECT, "T", "", "", "wes", "2020-01-01T09:00:00+00:00", "owner")

    RunsBackground.send_task_reminders(background.instance)
    RunsBackground.send_task_reminders(background.instance)

    assert len(background.sent) == 1
