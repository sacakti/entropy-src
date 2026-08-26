"""
Roles database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class RolesTable(DatabaseObject):
    """
    Stores Entropy authorization roles.
    """

    NAME = "roles"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the roles table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS roles
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL UNIQUE,

                description TEXT,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL
            )
            """
        )
