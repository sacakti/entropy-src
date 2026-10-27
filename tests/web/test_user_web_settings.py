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


def test_dashboard_layout_round_trip_and_checks(tmp_path: Path) -> None:
    import pytest
    from fastapi import HTTPException

    from core.web.routes.preferences import DashboardLayout, _check_layout, _dashboard

    repository = _repository(tmp_path)
    empty = {"widgets": [], "refresh_seconds": 5, "customized": False}
    assert _dashboard(repository.get_settings(3)) == empty

    layout = DashboardLayout(
        widgets=[
            {
                "id": "w1",
                "type": "tasks.list",
                "size": "large",
                "settings": {"filter": "mine", "limit": 8},
            },
            {"id": "w2", "type": "runs.summary", "size": "full"},
        ],
        refresh_seconds=30,
    )
    _check_layout(layout)
    stored = _dashboard(repository.update_settings(3, {"dashboard": layout.model_dump()}))
    assert stored["customized"] is True
    assert [widget["type"] for widget in stored["widgets"]] == ["tasks.list", "runs.summary"]
    assert stored["widgets"][0]["settings"] == {"filter": "mine", "limit": 8}

    # Reset: back to the web UI's default widgets.
    assert _dashboard(repository.update_settings(3, {"dashboard": None}))["customized"] is False

    with pytest.raises(HTTPException, match="used twice"):
        _check_layout(DashboardLayout(widgets=[{"id": "a", "type": "x"}, {"id": "a", "type": "y"}]))
    with pytest.raises(HTTPException, match="not a widget type"):
        _check_layout(DashboardLayout(widgets=[{"id": "a", "type": "Bad Type!"}]))
    with pytest.raises(HTTPException, match="too large"):
        big = {"id": "a", "type": "x", "settings": {"t": "x" * 5000}}
        _check_layout(DashboardLayout(widgets=[big]))
    with pytest.raises(ValueError):
        DashboardLayout(widgets=[{"id": "a", "type": "x", "size": "huge"}])
