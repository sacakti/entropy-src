"""Vision: messages for everyone, and turning it on or off."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core.web.routes import vision as routes
from lib.database.connection import DatabaseConnection
from lib.system.settings import SystemSettings
from lib.vision.broadcasts import KEEP, BroadcastError, BroadcastStore

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
RECORD = ("token", MagicMock(), SimpleNamespace(username="admin", id=1))


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


@pytest.fixture()
def store(connection) -> BroadcastStore:
    return BroadcastStore(connection)


def _request(connection) -> SimpleNamespace:
    context = SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))


def test_a_broadcast_is_active_until_it_expires(store) -> None:
    broadcast = store.create("  Upgrade at 18:00  ", "warning", "admin", 60, NOW)

    assert broadcast["message"] == "Upgrade at 18:00"
    assert [item["id"] for item in store.active(NOW + timedelta(minutes=59))] == [broadcast["id"]]
    assert store.active(NOW + timedelta(minutes=60)) == []


def test_no_duration_means_until_ended(store) -> None:
    broadcast = store.create("Maintenance", "info", "admin", 0, NOW)

    assert store.active(NOW + timedelta(days=365))

    assert store.end(broadcast["id"]) is True
    assert store.active(NOW) == []
    assert store.end(broadcast["id"]) is False


def test_newest_comes_first(store) -> None:
    first = store.create("One", "info", "admin", 60, NOW)
    second = store.create("Two", "info", "admin", 60, NOW)

    assert [item["id"] for item in store.active(NOW)] == [second["id"], first["id"]]


@pytest.mark.parametrize(
    ("message", "level", "duration"),
    [
        ("   ", "info", 60),
        ("x" * 501, "info", 60),
        ("ok", "party", 60),
        ("ok", "info", -1),
        ("ok", "info", 7 * 24 * 60 + 1),
    ],
)
def test_bad_broadcasts_are_refused(store, message, level, duration) -> None:
    with pytest.raises(BroadcastError):
        store.create(message, level, "admin", duration, NOW)

    assert store.active(NOW) == []


def test_old_broadcasts_are_removed(store, connection) -> None:
    for number in range(KEEP + 5):
        store.create(f"Message {number}", "info", "admin", 0, NOW)

    row = connection.fetchone("SELECT COUNT(*) AS n, MIN(id) AS low FROM vision_broadcasts")
    assert row["n"] == KEEP and row["low"] == 6


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------


def test_status_is_on_by_default_and_lists_active_messages(connection, store, monkeypatch) -> None:
    store.create("Hello", "info", "admin", 60)
    monkeypatch.setattr(routes, "current_project", lambda request, user: {"vision_activity": True})

    status = routes.vision_status(_request(connection), MagicMock(), RECORD)

    assert status["enabled"] is True
    assert [item["message"] for item in status["broadcasts"]] == ["Hello"]
    assert "ended_at" not in status["broadcasts"][0]


def test_turned_off_it_shows_nothing_and_cannot_send(connection, store, monkeypatch) -> None:
    store.create("Hello", "info", "admin", 60)
    SystemSettings(connection).update("vision", {"enabled": False})
    monkeypatch.setattr(routes, "require", lambda *arguments: None)

    status = routes.vision_status(_request(connection), MagicMock(), RECORD)
    assert status == {"enabled": False, "broadcasts": [], "project_activity": False}

    with pytest.raises(HTTPException) as caught:
        routes.send_broadcast(routes.BroadcastRequest(message="x"), _request(connection), RECORD)
    assert caught.value.status_code == 409


def test_sending_and_ending_need_the_settings_permission(connection, monkeypatch, store) -> None:
    checked = []
    monkeypatch.setattr(routes, "require", lambda request, user, name: checked.append(name))

    sent = routes.send_broadcast(
        routes.BroadcastRequest(message="Upgrade", level="warning", duration_minutes=15),
        _request(connection),
        RECORD,
    )
    routes.end_broadcast(sent["id"], _request(connection), RECORD)

    assert checked == ["system.settings", "system.settings"]
    assert sent["created_by"] == "admin" and store.active() == []


def test_no_permission_stops_it_before_anything_is_stored(connection, store, monkeypatch) -> None:
    def refuse(*arguments):
        raise HTTPException(status_code=403, detail="Forbidden")

    monkeypatch.setattr(routes, "require", refuse)

    with pytest.raises(HTTPException):
        routes.send_broadcast(routes.BroadcastRequest(message="x"), _request(connection), RECORD)

    assert store.active() == []


def test_ending_a_message_that_is_not_active_is_not_found(connection, monkeypatch) -> None:
    monkeypatch.setattr(routes, "require", lambda *arguments: None)

    with pytest.raises(HTTPException) as caught:
        routes.end_broadcast(99, _request(connection), RECORD)

    assert caught.value.status_code == 404


def test_a_bad_message_is_a_validation_error(connection, monkeypatch) -> None:
    monkeypatch.setattr(routes, "require", lambda *arguments: None)

    with pytest.raises(HTTPException) as caught:
        routes.send_broadcast(routes.BroadcastRequest(message="   "), _request(connection), RECORD)

    assert caught.value.status_code == 422
