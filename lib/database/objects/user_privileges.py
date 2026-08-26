"""
User privileges database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class UserPrivilegesTable(DatabaseObject):
    """
    Grants permissions directly to users.
    """

    NAME = "user_privileges"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the user_privileges table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_privileges
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                permission_id INTEGER NOT NULL,

                created_at TEXT NOT NULL,

                UNIQUE (
                    user_id,
                    permission_id
                ),

                FOREIGN KEY (
                    user_id
                )
                REFERENCES users (
                    id
                )
                ON DELETE CASCADE,

                FOREIGN KEY (
                    permission_id
                )
                REFERENCES permissions (
                    id
                )
                ON DELETE CASCADE
            )
            """
        )
