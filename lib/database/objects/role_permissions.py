"""
Role permissions database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class RolePermissionsTable(DatabaseObject):
    """
    Associates roles with permissions.
    """

    NAME = "role_permissions"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the role_permissions table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS role_permissions
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                role_id INTEGER NOT NULL,

                permission_id INTEGER NOT NULL,

                created_at TEXT NOT NULL,

                UNIQUE (
                    role_id,
                    permission_id
                ),

                FOREIGN KEY (
                    role_id
                )
                REFERENCES roles (
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
