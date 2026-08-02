"""
Users table.
"""

from lib.database.connection import DatabaseConnection

from lib.database.base import DatabaseObject


class UsersTable(DatabaseObject):

    NAME = "users"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,

                username        TEXT NOT NULL UNIQUE,

                password_hash   TEXT NOT NULL,

                full_name       TEXT,

                email           TEXT,

                group_id        INTEGER,

                system          INTEGER NOT NULL DEFAULT 0,

                is_active       INTEGER NOT NULL DEFAULT 1,

                created_at      TEXT NOT NULL,

                updated_at      TEXT NOT NULL
            )
            """
        )
