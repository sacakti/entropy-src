"""
The welcome tour in the web UI: shown once to people whose account is new.

Accounts that existed before the tour did are treated as having seen it;
anyone can replay it from Help.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SINCE_KEY = "onboarding.tour_since"


def _now() -> str:
    # The format of users.created_at (SQLite datetime('now'), UTC).
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Onboarding:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self._ensure()

    def _ensure(self) -> None:
        if getattr(self.connection, "_entropy_onboarding_ready", False):
            return
        from lib.database.objects.settings import SettingsTable

        SettingsTable().create(self.connection)
        with self.connection.transaction():
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS user_tours
                (
                    user_id  INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
                    done_at  TEXT
                )
                """)
            # On a fresh install (only the bootstrap administrator) everyone
            # is new; on an upgrade, only accounts made from now on.
            users = self.connection.fetchone("SELECT COUNT(*) AS n FROM users")
            fresh = users is None or users["n"] <= 1
            self.connection.execute(
                "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (SINCE_KEY, "" if fresh else _now(), _now()),
            )
        self.connection._entropy_onboarding_ready = True

    def _since(self) -> str:
        row = self.connection.fetchone("SELECT value FROM settings WHERE key = ?", (SINCE_KEY,))
        return row["value"] if row else ""

    def pending(self, user_id: int) -> bool:
        """Whether to show the tour when this user signs in."""

        row = self.connection.fetchone(
            "SELECT done_at FROM user_tours WHERE user_id = ?", (user_id,)
        )
        if row is not None:
            return row["done_at"] is None
        user = self.connection.fetchone("SELECT created_at FROM users WHERE id = ?", (user_id,))
        return bool(user and str(user["created_at"] or "") >= self._since())

    def finish(self, user_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "INSERT OR REPLACE INTO user_tours (user_id, done_at) VALUES (?, ?)",
                (user_id, _now()),
            )
