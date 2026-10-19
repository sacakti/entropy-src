"""Tests for profile pictures, web UI settings and background uploads."""

from __future__ import annotations

from pathlib import Path

from core.web.routes.backgrounds import _video_mime_type
from lib.database.connection import DatabaseConnection
from lib.database.repositories.user_web_settings import UserWebSettingsRepository


def _repository(tmp_path: Path) -> UserWebSettingsRepository:
    return UserWebSettingsRepository(DatabaseConnection(tmp_path / "entropy.db"))


def test_creates_tables_without_migration(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    assert repository.connection.table_exists("user_avatars")
    assert repository.connection.table_exists("user_web_settings")


def test_avatar_round_trip_and_version(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    assert repository.get_avatar(1) is None
    assert repository.avatar_version(1) is None

    repository.set_avatar(1, "image/png", b"first")
    first = repository.avatar_version(1)
    repository.set_avatar(1, "image/jpeg", b"second")

    mime_type, data, version = repository.get_avatar(1)

    assert (mime_type, data) == ("image/jpeg", b"second")
    assert version == repository.avatar_version(1)
    assert first is not None

    repository.delete_avatar(1)

    assert repository.get_avatar(1) is None


def test_settings_merge_top_level_keys(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    assert repository.get_settings(7) == {}

    repository.update_settings(7, {"wallpaper": {"shuffle": {"enabled": True}}})
    merged = repository.update_settings(7, {"other": 1})

    assert merged == {"wallpaper": {"shuffle": {"enabled": True}}, "other": 1}
    assert repository.get_settings(7) == merged
    assert repository.get_settings(8) == {}


def test_video_signatures() -> None:
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16
    webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 8 + b"webm" + b"\x00" * 8

    assert _video_mime_type(mp4) == "video/mp4"
    assert _video_mime_type(webm) == "video/webm"
    assert _video_mime_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16) is None
