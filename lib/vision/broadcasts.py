"""
Messages an administrator sends to everyone, for example before a server upgrade.

A broadcast stays active until it expires or is ended: everyone who has Entropy open sees
it, and so does anyone who signs in while it is active.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection

LEVELS = ("info", "warning", "error")
MAX_MESSAGE = 500
# 0 means until someone ends it.
MAX_DURATION_MINUTES = 7 * 24 * 60
# Ended and expired broadcasts kept, newest first.
KEEP = 100


class BroadcastError(ValueError):
    """A broadcast that cannot be sent; the message is safe to show."""


# A countdown shown live with the message, e.g. "Upgrade to 3.3.0 in 4:32".
COUNTDOWN_COLUMNS = (("countdown_to", "TEXT"), ("countdown_label", "TEXT"))


def ensure_broadcasts_schema(connection: DatabaseConnection) -> None:
    # Once per connection: every open page polls the broadcasts.
    if getattr(connection, "_entropy_broadcasts_ready", False):
        return
    connection.execute(
        "CREATE TABLE IF NOT EXISTS vision_broadcasts ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT NOT NULL,"
        "level TEXT NOT NULL DEFAULT 'info', created_by TEXT NOT NULL,"
        "created_at TEXT NOT NULL, expires_at TEXT, ended_at TEXT"
        ")"
    )
    existing = {row["name"] for row in connection.fetchall("PRAGMA table_info(vision_broadcasts)")}
    for name, declaration in COUNTDOWN_COLUMNS:
        if name not in existing:
            connection.execute(f"ALTER TABLE vision_broadcasts ADD COLUMN {name} {declaration}")
    connection._entropy_broadcasts_ready = True  # type: ignore[attr-defined]


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


class BroadcastStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_broadcasts_schema(connection)
        self.connection = connection

    def create(
        self,
        message: str,
        level: str,
        created_by: str,
        duration_minutes: int,
        now: Optional[datetime] = None,
        countdown_to: Optional[datetime] = None,
        countdown_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        A message for everyone. With `countdown_to`, pages show the time left to it
        live, after `countdown_label` (e.g. "Upgrade to 3.3.0 in 4:32").
        """
        text = message.strip()
        if not text:
            raise BroadcastError("Write the message to send.")
        if len(text) > MAX_MESSAGE:
            raise BroadcastError(f"The message can have at most {MAX_MESSAGE} characters.")
        if level not in LEVELS:
            raise BroadcastError(f"The level must be one of {', '.join(LEVELS)}.")
        if not 0 <= duration_minutes <= MAX_DURATION_MINUTES:
            raise BroadcastError("Choose how long the message stays, up to 7 days.")

        moment = now or datetime.now(timezone.utc)
        expires = _iso(moment + timedelta(minutes=duration_minutes)) if duration_minutes else None

        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO vision_broadcasts (message, level, created_by, created_at, expires_at,"
                " countdown_to, countdown_label) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    text,
                    level,
                    created_by,
                    _iso(moment),
                    expires,
                    _iso(countdown_to) if countdown_to else None,
                    (countdown_label or "").strip()[:80] or None,
                ),
            )
            self.connection.execute(
                "DELETE FROM vision_broadcasts WHERE id NOT IN"
                " (SELECT id FROM vision_broadcasts ORDER BY id DESC LIMIT ?)",
                (KEEP,),
            )
        row = self.connection.fetchone(
            "SELECT * FROM vision_broadcasts WHERE id = ?", (cursor.lastrowid,)
        )
        return dict(row)

    def active(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Broadcasts to show now, newest first."""

        moment = _iso(now or datetime.now(timezone.utc))
        rows = self.connection.fetchall(
            "SELECT * FROM vision_broadcasts WHERE ended_at IS NULL"
            " AND (expires_at IS NULL OR expires_at > ?) ORDER BY id DESC",
            (moment,),
        )
        return [dict(row) for row in rows]

    def end(self, broadcast_id: int, now: Optional[datetime] = None) -> bool:
        """Stop showing a broadcast; False when it was not active."""

        with self.connection.transaction():
            cursor = self.connection.execute(
                "UPDATE vision_broadcasts SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
                (_iso(now or datetime.now(timezone.utc)), broadcast_id),
            )
        return cursor.rowcount > 0
