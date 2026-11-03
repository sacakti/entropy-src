"""Task reminders and due-date alerts in Entropy, with and without SMTP."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from lib.database.connection import DatabaseConnection
from lib.runs.background import RunsBackground
from lib.system.mailer import MailError
from lib.tasks.store import TaskStore, ensure_tasks_schema

TODAY = date(2026, 11, 3)
ASSIGNEE, FOLLOWER, ACTOR = 1, 2, 3


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    ensure_tasks_schema(connection)
    with connection.transaction():
        connection.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, email TEXT,"
            " is_active INTEGER NOT NULL DEFAULT 1)"
        )
        for user_id, name in ((ASSIGNEE, "anna"), (FOLLOWER, "bob"), (ACTOR, "carl")):
            connection.execute(
                "INSERT INTO users (id, username, email) VALUES (?, ?, ?)",
                (user_id, name, f"{name}@example.com"),
            )
    return connection


@pytest.fixture()
def store(connection) -> TaskStore:
    return TaskStore(connection)


def _task(store: TaskStore, assignee: Any = "anna", **values: Any) -> int:
    reminder = values.pop("reminder_at", None)
    task_id = store.create(1, "Fix it", "Details", "", assignee, reminder, "carl", **values)["id"]
    store.follow(task_id, FOLLOWER, True)
    return task_id


@pytest.fixture()
def background(connection, monkeypatch):
    """A RunsBackground with its notifications and mail recorded."""

    sent: List[Dict[str, Any]] = []
    mails: List[List[str]] = []
    smtp = {"enabled": False}

    monkeypatch.setattr(
        "lib.system.settings.settings_for",
        lambda context: SimpleNamespace(values=lambda name: smtp),
    )

    def send_mail(settings, addresses, subject, text):
        mails.append(addresses)

    monkeypatch.setattr("lib.system.mailer.send_mail", send_mail)

    def notify(user_id, title, message, level, source="schedules"):
        sent.append(
            {"user": user_id, "title": title, "message": message, "level": level, "source": source}
        )

    instance = SimpleNamespace(_context=None, _connection=connection, _notify=notify)
    return SimpleNamespace(instance=instance, sent=sent, mails=mails, smtp=smtp)


def _remind(background) -> None:
    RunsBackground.send_task_reminders(background.instance)


def _due(background, monkeypatch, today: date = TODAY) -> None:
    monkeypatch.setattr("lib.runs.background.date", SimpleNamespace(today=lambda: today))
    RunsBackground.send_task_due_alerts(background.instance)


# ----------------------------------------------------------------------
# Reminders
# ----------------------------------------------------------------------


def test_a_reminder_reaches_assignee_and_followers_without_smtp(background, store) -> None:
    task = _task(store, reminder_at="2020-01-01T00:00:00")

    _remind(background)

    assert {item["user"] for item in background.sent} == {ASSIGNEE, FOLLOWER}
    assert all(item["source"] == f"task:{task}" for item in background.sent)
    assert "Fix it" in background.sent[0]["title"]
    assert background.mails == []


def test_a_reminder_is_sent_once(background, store) -> None:
    _task(store, reminder_at="2020-01-01T00:00:00")

    _remind(background)
    _remind(background)

    assert len(background.sent) == 2


def test_a_future_reminder_waits(background, store) -> None:
    _task(store, reminder_at="2999-01-01T00:00:00")

    _remind(background)

    assert background.sent == []


def test_a_follower_who_is_the_assignee_hears_once(background, store) -> None:
    task = _task(store, reminder_at="2020-01-01T00:00:00")
    store.follow(task, ASSIGNEE, True)

    _remind(background)

    assert sorted(item["user"] for item in background.sent) == [ASSIGNEE, FOLLOWER]


def test_a_task_nobody_watches_is_still_marked_sent(background, store, connection) -> None:
    task_id = store.create(1, "Alone", "", "", None, "2020-01-01T00:00:00", "carl")["id"]

    _remind(background)

    assert background.sent == []
    row = connection.fetchone("SELECT reminder_sent FROM tasks WHERE id = ?", (task_id,))
    assert row["reminder_sent"] == 1


def test_a_closed_task_stays_quiet(background, store) -> None:
    _task(store, reminder_at="2020-01-01T00:00:00", status="done")

    _remind(background)

    assert background.sent == [] and store.due_reminders() == []


def test_smtp_also_mails_the_assignee(background, store) -> None:
    background.smtp["enabled"] = True
    _task(store, reminder_at="2020-01-01T00:00:00")

    _remind(background)

    assert background.mails == [["anna@example.com"]]
    assert len(background.sent) == 2


def test_a_mail_failure_does_not_repeat_the_in_app_reminder(background, store, monkeypatch) -> None:
    background.smtp["enabled"] = True
    _task(store, reminder_at="2020-01-01T00:00:00")

    def fail(*arguments):
        raise MailError("down")

    monkeypatch.setattr("lib.system.mailer.send_mail", fail)

    _remind(background)
    _remind(background)

    assert len(background.sent) == 2


# ----------------------------------------------------------------------
# Due dates
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("offset", "title", "level"),
    [
        (1, "Task due tomorrow", "info"),
        (0, "Task due today", "warning"),
        (-3, "Task overdue", "warning"),
    ],
)
def test_due_stages(background, store, monkeypatch, offset, title, level) -> None:
    task = _task(store, due_date=(TODAY + timedelta(days=offset)).isoformat())

    _due(background, monkeypatch)

    assert {item["user"] for item in background.sent} == {ASSIGNEE, FOLLOWER}
    assert background.sent[0]["title"].startswith(title)
    assert background.sent[0]["level"] == level
    assert background.sent[0]["source"] == f"task:{task}"


def test_later_due_dates_and_closed_tasks_stay_quiet(background, store, monkeypatch) -> None:
    _task(store, due_date=(TODAY + timedelta(days=2)).isoformat())
    _task(store, due_date=TODAY.isoformat(), status="done")

    _due(background, monkeypatch)

    assert background.sent == []


def test_each_stage_alerts_once_as_days_pass(background, store, monkeypatch) -> None:
    _task(store, assignee=None, due_date=TODAY.isoformat())

    for day in (-1, -1, 0, 0, 1, 2, 30):
        _due(background, monkeypatch, TODAY + timedelta(days=day))

    titles = [item["title"].split(":")[0] for item in background.sent]
    assert titles == ["Task due tomorrow", "Task due today", "Task overdue"]


def test_a_new_due_date_alerts_again(background, store, monkeypatch) -> None:
    task = _task(store, assignee=None, due_date=TODAY.isoformat())
    _due(background, monkeypatch)

    store.update(task, {"due_date": (TODAY + timedelta(days=1)).isoformat()})
    _due(background, monkeypatch)

    assert len(background.sent) == 2
    assert background.sent[1]["title"].startswith("Task due tomorrow")
