"""`ent upgrade` warns everyone with Entropy open first, like Administration → Upgrade."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

import pytest

from core.commands import upgrade as command_module
from core.commands.upgrade import UpgradeCommand
from lib.database.connection import DatabaseConnection
from lib.system import web
from lib.vision.broadcasts import BroadcastStore


class Ui:
    def __init__(self) -> None:
        self.lines: List[str] = []

    def info(self, text: str) -> None:
        self.lines.append(text)

    warning = success = error = info


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


def _command(connection: Any) -> UpgradeCommand:
    context = SimpleNamespace(
        ui=Ui(),
        authorization=SimpleNamespace(require=lambda session, permission: None),
        session_manager=SimpleNamespace(require=lambda: SimpleNamespace(username="admin")),
        database_manager=SimpleNamespace(connection=connection) if connection else None,
    )
    return UpgradeCommand(context)  # type: ignore[arg-type]


def _active(connection: DatabaseConnection) -> List[str]:
    return [item["message"] for item in BroadcastStore(connection).active()]


@pytest.fixture()
def web_running(monkeypatch) -> None:
    monkeypatch.setattr(web, "status", lambda: {"running": True})


def test_everyone_is_warned_during_the_upgrade_and_the_warning_ends_after(
    connection, web_running
) -> None:
    command = _command(connection)

    with command._notice("upgrade", "3.3.0", "admin", 0) as go:
        assert go is True
        [warning] = _active(connection)
        assert "being upgraded to 3.3.0 by admin" in warning

    assert _active(connection) == []


def test_a_failed_upgrade_still_takes_the_warning_down(connection, web_running) -> None:
    command = _command(connection)

    with (
        pytest.raises(RuntimeError, match="disk full"),
        command._notice("upgrade", "3.3.0", "admin", 0),
    ):
        raise RuntimeError("disk full")

    assert _active(connection) == []


def test_without_a_web_server_nobody_is_warned_and_nothing_waits(connection, monkeypatch) -> None:
    monkeypatch.setattr(web, "status", lambda: {"running": False})
    command = _command(connection)
    command._wait = lambda action, starts_at: pytest.fail("no one to wait for")  # type: ignore[method-assign]

    with command._notice("upgrade", "3.3.0", "admin", 5) as go:
        assert go is True and _active(connection) == []


def test_ctrl_c_during_the_wait_cancels_and_takes_the_warning_down(connection, web_running) -> None:
    command = _command(connection)
    command._wait = lambda action, starts_at: False  # type: ignore[method-assign]

    with command._notice("rollback", "3.1.0", "admin", 5) as go:
        assert go is False
        assert "rolled back to 3.1.0 at" in _active(connection)[0]

    assert _active(connection) == []
    assert command._ui.lines[-1] == "Cancelled; nothing was rolled back and the warning is down."


def test_the_wait_counts_down_by_the_minute_and_ctrl_c_stops_it(monkeypatch) -> None:
    start = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    clock = {"now": start}

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            return clock["now"]

    def sleep(seconds: float) -> None:
        clock["now"] += timedelta(seconds=seconds)

    monkeypatch.setattr(command_module, "datetime", Clock)
    monkeypatch.setattr(command_module.time, "sleep", sleep)
    command = _command(None)

    assert command._wait("upgrade", start + timedelta(minutes=3)) is True
    lines = command._ui.lines
    assert lines[0].startswith("Everyone with Entropy open was warned. The upgrade starts in 3")
    assert lines[1:] == ["2 minute(s) to go...", "1 minute(s) to go..."]

    def interrupted(seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(command_module.time, "sleep", interrupted)
    assert command._wait("upgrade", clock["now"] + timedelta(minutes=1)) is False


@pytest.mark.parametrize("minutes", [-1, 61])
def test_the_notice_is_0_to_60_minutes(minutes: int) -> None:
    command = _command(None)
    arguments = Namespace(notice=minutes, rollback=True, source=None, yes=True, check=False)

    with pytest.raises(ValueError, match="--notice"):
        command.execute(arguments)
