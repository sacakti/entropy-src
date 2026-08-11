"""
Workflow definition registry.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class WorkflowRegistryTable(DatabaseObject):

    NAME = "workflow_registry"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_registry
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,

                name            TEXT NOT NULL UNIQUE,

                version         TEXT NOT NULL,

                description     TEXT,

                definition      TEXT NOT NULL,

                created_at      TEXT NOT NULL,

                updated_at      TEXT NOT NULL
            )
            """
        )
