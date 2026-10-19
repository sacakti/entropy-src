"""
Notifications table.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class NotificationsTable(DatabaseObject):

    NAME = "notifications"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications
            (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                title       TEXT NOT NULL,
                message     TEXT NOT NULL DEFAULT '',
                level       TEXT NOT NULL DEFAULT 'info'
                    CHECK (level IN ('info', 'success', 'warning', 'error')),
                source      TEXT,
                is_read     INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notifications_user
            ON notifications (user_id, is_read, created_at)
            """
        )
