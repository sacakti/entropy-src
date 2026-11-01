"""
Browser sign-ins: when and from where each user last signed in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_logins (
    user_id INTEGER PRIMARY KEY,
    last_login_at TEXT NOT NULL,
    last_login_address TEXT,
    previous_login_at TEXT,
    previous_login_address TEXT
)
"""


class UserLoginsRepository(Repository):
    """
    The latest and the previous browser sign-in of each user.

    The previous one is what a user is shown after signing in ("last
    sign-in"): an unexpected time or address is a sign someone else used
    the account.
    """

    def __init__(self, connection: DatabaseConnection) -> None:
        super().__init__(connection)
        if not getattr(connection, "_entropy_user_logins_ready", False):
            connection.execute(SCHEMA)
            # Remembered on the connection: the statement is idempotent anyway.
            setattr(connection, "_entropy_user_logins_ready", True)  # noqa: B010 - not a declared attribute

    def record(self, user_id: int, address: Optional[str]) -> None:
        """A new sign-in: the latest becomes the previous one."""

        now = datetime.now(timezone.utc).isoformat()
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO user_logins(user_id, last_login_at, last_login_address)"
                " VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET"
                " previous_login_at = user_logins.last_login_at,"
                " previous_login_address = user_logins.last_login_address,"
                " last_login_at = excluded.last_login_at,"
                " last_login_address = excluded.last_login_address",
                (user_id, now, address),
            )

    def get(self, user_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM user_logins WHERE user_id = ?", (user_id,))
        return dict(row) if row else None

    def previous(self, user_id: int) -> Optional[Dict[str, Any]]:
        """The sign-in before the current one, or None for a first sign-in."""

        row = self.get(user_id)
        if not row or not row["previous_login_at"]:
            return None
        return {"at": row["previous_login_at"], "address": row["previous_login_address"]}

    def latest(self, user_ids: Iterable[int]) -> Dict[int, str]:
        """Latest sign-in time of each user that has signed in (for administration)."""

        ids = list(user_ids)
        if not ids:
            return {}
        marks = ",".join("?" for _ in ids)
        rows = self.connection.fetchall(
            f"SELECT user_id, last_login_at FROM user_logins WHERE user_id IN ({marks})",
            tuple(ids),
        )
        return {int(row["user_id"]): row["last_login_at"] for row in rows}
