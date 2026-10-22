"""entropy.db safety: lock, guard, backups, recovery."""

from __future__ import annotations

import os
import sqlite3

import pytest

from lib.database.connection import DatabaseConnection
from lib.database.safety import (
    DatabaseLockedError,
    DatabaseSafety,
    DatabaseSafetyError,
    check_file,
)


def _database(path, rows=3) -> DatabaseConnection:
    connection = DatabaseConnection(path)
    connection.open()
    with connection.transaction():
        connection.execute("CREATE TABLE IF NOT EXISTS things (id INTEGER PRIMARY KEY, name TEXT)")
        for number in range(rows):
            connection.execute("INSERT INTO things (name) VALUES (?)", (f"thing {number}",))
    return connection


def _count(path) -> int:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT count(*) FROM things").fetchone()[0]


def test_one_server_per_database(tmp_path) -> None:
    first = DatabaseSafety(tmp_path / "entropy.db")
    first.acquire_server_lock()
    second = DatabaseSafety(tmp_path / "entropy.db")
    with pytest.raises(DatabaseLockedError, match=f"pid {os.getpid()}"):
        second.acquire_server_lock()
    first.release_server_lock()
    second.acquire_server_lock()
    second.release_server_lock()


def test_a_deleted_database_comes_back_from_its_guard(tmp_path) -> None:
    path = tmp_path / "entropy.db"
    connection = _database(path)
    safety = DatabaseSafety(path)
    safety.refresh_guard()
    assert os.path.samefile(path, safety.guard)

    path.unlink()  # someone deletes it while the server runs
    message = safety._watch_once(lambda: connection.connection, connection.reopen)
    assert "guard" in message and path.exists()
    # Same data, and writes keep going to it.
    with connection.transaction():
        connection.execute("INSERT INTO things (name) VALUES ('after')")
    assert _count(path) == 4
    connection.close()


def test_database_and_guard_deleted_rebuilds_from_the_open_connection(tmp_path) -> None:
    path = tmp_path / "entropy.db"
    connection = _database(path)
    safety = DatabaseSafety(path)
    safety.refresh_guard()
    path.unlink()
    safety.guard.unlink()
    message = safety._watch_once(lambda: connection.connection, connection.reopen)
    assert "rebuilt" in message
    assert _count(path) == 3 and os.path.samefile(path, safety.guard)
    with connection.transaction():
        connection.execute("INSERT INTO things (name) VALUES ('after')")
    assert _count(path) == 4
    connection.close()


def test_backups_are_checked_rotated_and_used_when_the_file_is_gone(tmp_path) -> None:
    path = tmp_path / "entropy.db"
    connection = _database(path)
    safety = DatabaseSafety(path)
    safety.save_settings({"keep": 2, "backup_dir": str(tmp_path / "elsewhere")})
    names = []
    for number in range(3):
        with connection.transaction():
            connection.execute("INSERT INTO things (name) VALUES (?)", (f"more {number}",))
        names.append(safety.backup(connection.connection, reason=f"t{number}")["name"])
    kept = [entry["name"] for entry in safety.backups()]
    assert kept == [names[2], names[1]]  # newest first, the oldest rotated away
    assert all(check_file(tmp_path / "elsewhere" / name) == "ok" for name in kept)
    connection.close()

    # No guard and no file: a new process restores the newest good backup
    # instead of starting an empty database.
    path.unlink()
    assert not safety.guard.exists()
    message = DatabaseSafety(path).ensure_present()
    assert names[2] in message and _count(path) == 6


def test_a_damaged_database_is_replaced_at_server_start(tmp_path) -> None:
    path = tmp_path / "entropy.db"
    connection = _database(path)
    safety = DatabaseSafety(path)
    safety.backup(connection.connection)
    connection.close()
    path.write_bytes(b"this is not a database" * 100)

    message = safety.server_start(reopen=lambda: None, close=lambda: None)
    safety.release_server_lock()
    assert "damaged" in message and _count(path) == 3
    kept = [p.name for p in tmp_path.iterdir() if p.name.startswith("entropy.db.damaged-")]
    assert len(kept) == 1


def test_damaged_without_backup_refuses_to_start(tmp_path) -> None:
    path = tmp_path / "entropy.db"
    path.write_bytes(b"garbage" * 500)
    safety = DatabaseSafety(path)
    with pytest.raises(DatabaseSafetyError, match="no good backup"):
        safety.server_start(reopen=lambda: None, close=lambda: None)
    safety.release_server_lock()
    assert path.read_bytes().startswith(b"garbage")  # nothing touched


def test_restore_keeps_the_replaced_file(tmp_path) -> None:
    path = tmp_path / "entropy.db"
    connection = _database(path)
    safety = DatabaseSafety(path)
    name = safety.backup(connection.connection)["name"]
    with connection.transaction():
        connection.execute("DELETE FROM things")
    connection.close()
    message = safety.restore(name)
    assert "previous database is kept" in message and _count(path) == 3
    with pytest.raises(DatabaseSafetyError):
        safety.restore("../../etc/passwd")


def test_settings_are_validated(tmp_path) -> None:
    safety = DatabaseSafety(tmp_path / "entropy.db")
    with pytest.raises(DatabaseSafetyError):
        safety.save_settings({"interval_hours": 0})
    with pytest.raises(DatabaseSafetyError):
        safety.save_settings({"backup_dir": "relative/path"})
    assert safety.save_settings({"interval_hours": 1, "keep": 5})["keep"] == 5
    assert safety.settings()["interval_hours"] == 1
