"""The welcome tour is shown once, to new accounts only."""

from __future__ import annotations

from lib.users.onboarding import SINCE_KEY, Onboarding


def _user(connection, name: str, created_at: str) -> int:
    cursor = connection.execute(
        "INSERT INTO users (username, password_hash, is_active, created_at, updated_at)"
        " VALUES (?, 'x', 1, ?, ?)",
        (name, created_at, created_at),
    )
    connection.commit()
    return cursor.lastrowid


def test_fresh_install_shows_the_tour_to_everyone(connection) -> None:
    admin = _user(connection, "admin", "2026-01-01 00:00:00")
    tours = Onboarding(connection)

    assert tours.pending(admin)
    tours.finish(admin)
    assert not tours.pending(admin)


def test_upgrade_shows_the_tour_to_new_accounts_only(connection) -> None:
    old = _user(connection, "admin", "2026-01-01 00:00:00")
    _user(connection, "alice", "2026-01-02 00:00:00")
    tours = Onboarding(connection)
    since = connection.fetchone("SELECT value FROM settings WHERE key = ?", (SINCE_KEY,))["value"]
    new = _user(connection, "bob", since)

    assert not tours.pending(old)
    assert tours.pending(new)
    # A second start does not move the cut-off.
    connection._entropy_onboarding_ready = False
    Onboarding(connection)
    assert tours.pending(new)
