"""
Group roles database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class GroupRolesTable(DatabaseObject):
    """
    Associates groups with roles.
    """

    NAME = "group_roles"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the group_roles table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS group_roles
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                group_id INTEGER NOT NULL,

                role_id INTEGER NOT NULL,

                created_at TEXT NOT NULL,

                UNIQUE (
                    group_id,
                    role_id
                ),

                FOREIGN KEY (
                    group_id
                )
                REFERENCES groups (
                    id
                )
                ON DELETE CASCADE,

                FOREIGN KEY (
                    role_id
                )
                REFERENCES roles (
                    id
                )
                ON DELETE CASCADE
            )
            """
        )
