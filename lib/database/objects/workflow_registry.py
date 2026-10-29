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

                -- Workflows are project scoped: a name is unique per project.
                project_id      INTEGER NOT NULL,

                name            TEXT NOT NULL,

                version         TEXT NOT NULL,

                description     TEXT,

                definition      TEXT NOT NULL,

                created_at      TEXT NOT NULL,

                updated_at      TEXT NOT NULL,

                UNIQUE (project_id, name)
            )
            """
        )
