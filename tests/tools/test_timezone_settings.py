"""The installation's time zone setting and the server time zone lookup."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lib.database.connection import DatabaseConnection
from lib.system import timezone
from lib.system.settings import SettingsError, SystemSettings


def test_valid_timezone() -> None:
    assert timezone.valid_timezone("Europe/Berlin")
    assert timezone.valid_timezone("UTC")
    for name in ("", "Mars/Olympus", "../etc/passwd", "/etc/localtime", "x" * 65):
        assert not timezone.valid_timezone(name)


def test_server_timezone_prefers_tz_and_falls_back_to_utc(monkeypatch: Any) -> None:
    monkeypatch.setenv("TZ", ":Asia/Tokyo")
    assert timezone.server_timezone() == "Asia/Tokyo"

    monkeypatch.setenv("TZ", "Not/AZone")
    monkeypatch.setattr(timezone.Path, "is_symlink", lambda self: False)
    monkeypatch.setattr(
        timezone.Path, "read_text", lambda self, encoding=None: (_ for _ in ()).throw(OSError())
    )
    assert timezone.server_timezone() == "UTC"


def test_zone_from_localtime_link(tmp_path: Path) -> None:
    target = tmp_path / "zoneinfo" / "posix" / "America" / "New_York"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")
    link = tmp_path / "localtime"
    link.symlink_to(target)
    assert timezone._from_localtime(link) == "America/New_York"


def test_general_timezone_defaults_empty_and_is_validated(tmp_path: Path) -> None:
    store = SystemSettings(DatabaseConnection(tmp_path / "entropy.db"))
    assert store.get("general")["timezone"] == ""

    assert store.update("general", {"timezone": "Europe/Berlin"})["timezone"] == "Europe/Berlin"
    with pytest.raises(SettingsError, match="not a time zone"):
        store.update("general", {"timezone": "Mars/Olympus"})
    assert store.get("general")["timezone"] == "Europe/Berlin"

    assert store.update("general", {"timezone": ""})["timezone"] == ""


def test_profile_reports_and_saves_the_users_timezone(tmp_path: Path, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from fastapi import HTTPException, Response

    import lib.auth.external
    from core.web.routes import profile
    from lib.models.users import User

    class NoProvider:
        def __init__(self, context: Any) -> None:
            pass

        def provider_of(self, user_id: int) -> None:
            return None

    monkeypatch.setattr(lib.auth.external, "ExternalAccounts", NoProvider)
    monkeypatch.setattr(profile, "server_timezone", lambda: "Asia/Kuwait")

    connection = DatabaseConnection(tmp_path / "entropy.db")
    user = User(id=1, username="ada")
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        user_manager=SimpleNamespace(update_profile=lambda user, full_name, email: user),
    )
    request: Any = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(entropy_context=context))
    )
    record: Any = (None, "", user)

    def get() -> dict:
        return profile.get_profile(request, Response(), record)

    def patch(**changes: Any) -> dict:
        payload = profile.ProfileUpdate(full_name=None, email=None, **changes)
        return profile.update_profile(payload, request, Response(), record)

    body = get()
    assert body["timezone"] is None
    assert body["default_timezone"] == body["effective_timezone"] == "Asia/Kuwait"

    SystemSettings(connection).update("general", {"timezone": "Europe/Berlin"})
    assert get()["effective_timezone"] == "Europe/Berlin"

    saved = patch(timezone="America/New_York")
    assert saved["timezone"] == saved["effective_timezone"] == "America/New_York"
    assert saved["server_timezone"] == "Asia/Kuwait"

    # Left out: unchanged. None: follow the installation's zone again.
    assert patch()["timezone"] == "America/New_York"
    cleared = patch(timezone=None)
    assert cleared["timezone"] is None and cleared["effective_timezone"] == "Europe/Berlin"

    with pytest.raises(HTTPException) as error:
        patch(timezone="Mars/Olympus")
    assert error.value.status_code == 422
