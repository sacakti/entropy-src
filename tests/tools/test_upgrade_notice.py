"""Everyone is warned through Vision before Entropy is upgraded, and the warning stops after."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from core.version import VERSION
from core.web.routes import system
from lib.database.connection import DatabaseConnection
from lib.models.users import User
from lib.system import upgrade_notice
from lib.system.settings import SystemSettings
from lib.vision.broadcasts import BroadcastStore

ADMIN = User(id=1, username="admin")


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


@pytest.fixture()
def home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(system.install, "entropy_home", lambda: tmp_path / "home")
    return tmp_path / "home"


def _active(connection: DatabaseConnection) -> List[str]:
    return [item["message"] for item in BroadcastStore(connection).active()]


def _wait() -> None:
    for _ in range(300):
        if not system._ACTIVE.is_set():
            return
        time.sleep(0.01)
    raise AssertionError("the job did not finish")


# ----------------------------------------------------------------------
# The message
# ----------------------------------------------------------------------


def test_the_warning_names_when_it_starts_in_the_installations_zone(connection) -> None:
    SystemSettings(connection).update("general", {"timezone": "Asia/Kuwait"})
    starts = datetime(2026, 11, 10, 11, 30, tzinfo=timezone.utc)

    notice = upgrade_notice.announce(connection, "upgrade", "3.3.0", "admin", starts, 5)

    [warning] = BroadcastStore(connection).active()
    assert warning["id"] == notice["id"] and warning["level"] == "warning"
    assert "upgraded to 3.3.0 at 14:30 (Asia/Kuwait), in 5 minutes, by admin" in warning["message"]
    # Pages count down to it live.
    assert warning["countdown_to"] == "2026-11-10T11:30:00+00:00"
    assert warning["countdown_label"] == "Upgrade to 3.3.0"
    assert "Save your work before then" in warning["message"]


def test_without_a_wait_it_says_now() -> None:
    text = upgrade_notice.message_for("rollback", "3.1.0", "admin", None, ZoneInfo("UTC"), 0)
    assert text.startswith("Entropy is being rolled back to 3.1.0 by admin")
    assert "Save your work now" in text


def test_ending_stops_the_warning_and_says_nothing_more(connection) -> None:
    notice = upgrade_notice.announce(connection, "upgrade", "3.3.0", "admin")

    upgrade_notice.end(connection, notice)

    assert _active(connection) == []


def test_a_broadcast_that_only_shares_the_id_is_left_alone(connection) -> None:
    # After a database restore the id can name someone else's broadcast.
    other = BroadcastStore(connection).create("Maintenance at 6", "info", "ops", 0)

    upgrade_notice.end(connection, {"id": other["id"], "created_at": "2020-01-01T00:00:00+00:00"})

    assert _active(connection) == ["Maintenance at 6"]


# ----------------------------------------------------------------------
# The job
# ----------------------------------------------------------------------


def test_the_upgrade_waits_for_people_then_runs(connection, home, monkeypatch) -> None:
    waited: List[float] = []
    restarts: List[bool] = []
    monkeypatch.setattr(system.web, "reexec_current_server", lambda: restarts.append(True))
    # A minute of notice, passed at once.
    monkeypatch.setattr(system._CANCEL, "wait", lambda seconds: waited.append(seconds) or False)

    job = system._start(
        "upgrade", ADMIN, VERSION, lambda progress: {"to": VERSION}, connection, notice_minutes=1
    )
    assert job["state"] == "waiting" and job["starts_at"] > job["started_at"]
    assert "in 1 minute," in _active(connection)[0]
    _wait()

    stored = system._read_job()
    assert waited == [60] and restarts == [True] and stored["state"] == "restarting"
    assert any(line["message"] == "Starting now." for line in stored["log"])
    # Ended by this server just before it restarted, so a new version that does not
    # know the notice cannot leave it up; nothing is broadcast after.
    assert _active(connection) == [] and system._read_job()["notice_ended"]
    context = SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
    system.settle_after_restart(context)
    assert _active(connection) == []


def test_the_new_server_ends_a_notice_left_by_one_that_died(connection, home) -> None:
    notice = upgrade_notice.announce(connection, "upgrade", "3.3.0", "admin")
    system._write_job({"state": "running", "notice": notice, "log": []})

    system.settle_after_restart(
        SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
    )

    assert _active(connection) == [] and system._read_job()["notice_ended"]


def test_a_waiting_upgrade_can_be_cancelled(connection, home, monkeypatch) -> None:
    worked: List[bool] = []
    record: Any = (None, "", ADMIN)
    request: Any = SimpleNamespace()
    monkeypatch.setattr(system, "_admin", lambda request, record: ADMIN)

    system._start(
        "upgrade",
        ADMIN,
        "3.3.0",
        lambda progress: worked.append(True),
        connection,
        notice_minutes=5,
    )
    system.cancel_upgrade(request, record)
    _wait()
    stored = system._read_job()
    with pytest.raises(HTTPException) as late:
        system.cancel_upgrade(request, record)

    assert worked == [] and stored["state"] == "cancelled"
    assert stored["log"][-1]["message"] == "The upgrade was cancelled."
    assert _active(connection) == [] and late.value.status_code == 409


def test_a_failed_rollback_stops_the_warning_at_once(connection, home) -> None:
    def broken(progress: Any) -> Any:
        raise RuntimeError("disk full")

    system._start("rollback", ADMIN, "3.1.0", broken, connection)
    _wait()

    assert system._read_job()["state"] == "failed"
    assert _active(connection) == []


def test_an_older_broadcasts_table_gets_the_countdown_columns(tmp_path) -> None:
    connection = DatabaseConnection(tmp_path / "old.db")
    connection.execute(
        "CREATE TABLE vision_broadcasts (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " message TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'info', created_by TEXT NOT NULL,"
        " created_at TEXT NOT NULL, expires_at TEXT, ended_at TEXT)"
    )

    BroadcastStore(connection).create("Old style", "info", "ops", 0)

    [item] = BroadcastStore(connection).active()
    assert item["countdown_to"] is None and item["countdown_label"] is None
