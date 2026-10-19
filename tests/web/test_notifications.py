"""Tests for the notification center repository."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lib.database.connection import DatabaseConnection
from lib.database.repositories import notifications as module
from lib.database.repositories.notifications import NotificationRepository, notify_user


def _repository(tmp_path: Path) -> NotificationRepository:
    return NotificationRepository(DatabaseConnection(tmp_path / "entropy.db"))


def test_create_list_and_unread(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    first = repository.create(1, "Upload complete", "3 files", "success", "wallpapers")
    repository.create(1, "Other", level="nonsense")
    repository.create(2, "Someone else")

    items = repository.list(1)

    assert [item["title"] for item in items] == ["Other", "Upload complete"]
    assert items[0]["level"] == "info"
    assert first["read"] is False
    assert repository.unread_count(1) == 2


def test_read_and_delete_are_scoped_to_the_user(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    mine = repository.create(1, "Mine")

    assert repository.mark_read(2, mine["id"]) == 0
    assert repository.mark_read(1, mine["id"]) == 1
    assert repository.unread_count(1) == 0
    assert repository.delete(2, mine["id"]) == 0
    assert repository.delete(1) == 1
    assert repository.list(1) == []


def test_old_notifications_are_pruned(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(module, "MAX_PER_USER", 3)
    repository = _repository(tmp_path)

    for index in range(5):
        repository.create(1, f"n{index}")

    assert [item["title"] for item in repository.list(1)] == ["n4", "n3", "n2"]


def test_notify_user_never_raises() -> None:
    notify_user(None, 1, "x")
    notify_user(SimpleNamespace(database_manager=None), 1, "x")
    notify_user(SimpleNamespace(database_manager=SimpleNamespace(connection=object())), 1, "x")
