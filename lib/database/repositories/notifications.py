"""
Notification repository.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection
from lib.database.objects.notifications import NotificationsTable
from lib.database.repository import Repository

LEVELS = ("info", "success", "warning", "error")

# Notifications kept per user; older ones are pruned on insert.
MAX_PER_USER = 200


class NotificationRepository(Repository):
    """
    Per-user notifications for the web notification center.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:
        super().__init__(connection)

        # Servers upgraded without `ent migrate` still get the table.
        if not getattr(connection, "_entropy_notifications_ready", False):
            with self.connection.transaction():
                NotificationsTable().create(connection)

            # Remembered on the connection: ids can be reused by new objects.
            setattr(connection, "_entropy_notifications_ready", True)

    @staticmethod
    def _payload(row: Any) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "message": row["message"],
            "level": row["level"],
            "source": row["source"],
            "read": bool(row["is_read"]),
            "created_at": row["created_at"],
        }

    def create(
        self,
        user_id: int,
        title: str,
        message: str = "",
        level: str = "info",
        source: Optional[str] = None,
    ) -> Dict[str, Any]:

        if level not in LEVELS:
            level = "info"

        with self.connection.transaction():
            cursor = self.execute(
                """
                INSERT INTO notifications
                    (user_id, title, message, level, source, is_read, created_at)
                VALUES (?, ?, ?, ?, ?, 0, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                """,
                (user_id, title[:200], message[:2000], level, source),
            )
            notification_id = cursor.lastrowid

            self.execute(
                """
                DELETE FROM notifications
                WHERE user_id = ?
                  AND id NOT IN (
                      SELECT id FROM notifications
                      WHERE user_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (user_id, user_id, MAX_PER_USER),
            )

        row = self.fetchone("SELECT * FROM notifications WHERE id = ?", (notification_id,))
        return self._payload(row)

    def list(
        self,
        user_id: int,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:

        rows = self.fetchall(
            """
            SELECT * FROM notifications
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )

        return [self._payload(row) for row in rows]

    def unread_count(
        self,
        user_id: int,
    ) -> int:

        row = self.fetchone(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
            (user_id,),
        )
        return int(row[0])

    def mark_read(
        self,
        user_id: int,
        notification_id: Optional[int] = None,
    ) -> int:
        """Mark one notification, or all when no id is given, as read."""

        with self.connection.transaction():
            if notification_id is None:
                cursor = self.execute(
                    "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
                    (user_id,),
                )
            else:
                cursor = self.execute(
                    "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND id = ?",
                    (user_id, notification_id),
                )

        return cursor.rowcount

    def delete(
        self,
        user_id: int,
        notification_id: Optional[int] = None,
    ) -> int:
        """Delete one notification, or all when no id is given."""

        with self.connection.transaction():
            if notification_id is None:
                cursor = self.execute(
                    "DELETE FROM notifications WHERE user_id = ?",
                    (user_id,),
                )
            else:
                cursor = self.execute(
                    "DELETE FROM notifications WHERE user_id = ? AND id = ?",
                    (user_id, notification_id),
                )

        return cursor.rowcount


def notify_user(
    context: Any,
    user_id: Optional[int],
    title: str,
    message: str = "",
    level: str = "info",
    source: Optional[str] = None,
) -> None:
    """Best-effort notification from server-side events; never raises."""

    if user_id is None or context is None or context.database_manager is None:
        return

    try:
        NotificationRepository(context.database_manager.connection).create(
            user_id, title, message, level, source,
        )
    except Exception:  # noqa: BLE001 - notifications must not break the action
        pass
