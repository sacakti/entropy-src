"""
User roles database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class UserRolesTable(DatabaseObject):
    """
    Associates users directly with roles.
    """

    NAME = "user_roles"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the user_roles table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_roles
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                role_id INTEGER NOT NULL,

                created_at TEXT NOT NULL,

                UNIQUE (
                    user_id,
                    role_id
                ),

                FOREIGN KEY (
                    user_id
                )
                REFERENCES users (
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
