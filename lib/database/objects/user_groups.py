"""
User groups database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class UserGroupsTable(DatabaseObject):
    """
    Associates users with groups.
    """

    NAME = "user_groups"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the user_groups table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_groups
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                group_id INTEGER NOT NULL,

                created_at TEXT NOT NULL,

                UNIQUE (
                    user_id,
                    group_id
                ),

                FOREIGN KEY (
                    user_id
                )
                REFERENCES users (
                    id
                )
                ON DELETE CASCADE,

                FOREIGN KEY (
                    group_id
                )
                REFERENCES groups (
                    id
                )
                ON DELETE CASCADE
            )
            """
        )
