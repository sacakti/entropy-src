"""
Permissions database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class PermissionsTable(DatabaseObject):
    """
    Stores Entropy authorization permissions.
    """

    NAME = "permissions"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the permissions table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS permissions
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                module_id INTEGER NOT NULL,

                name TEXT NOT NULL UNIQUE,

                description TEXT,

                permission_type TEXT NOT NULL,

                FOREIGN KEY (
                    module_id
                )
                REFERENCES modules (
                    id
                )
                ON DELETE CASCADE
            )
            """
        )
