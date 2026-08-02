"""
Migration history table.
"""

from lib.database.connection import DatabaseConnection

from lib.database.base import DatabaseObject


class SchemaMigrationsTable(DatabaseObject):

    NAME = "schema_migrations"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations
            (
                version     INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at  TEXT NOT NULL
            )
            """
        )
