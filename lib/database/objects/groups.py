"""
Groups database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class GroupsTable(DatabaseObject):
    """
    Stores Entropy user groups.
    """

    NAME = "groups"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the groups table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS groups
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL UNIQUE,

                description TEXT,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL
            )
            """
        )
