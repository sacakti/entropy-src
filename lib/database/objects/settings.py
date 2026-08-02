"""
Application settings table.
"""

from lib.database.connection import DatabaseConnection

from lib.database.base import DatabaseObject


class SettingsTable(DatabaseObject):

    NAME = "settings"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings
            (
                key         TEXT PRIMARY KEY,
                value       TEXT,
                updated_at  TEXT
            )
            """
        )
