"""
Workflow execution history.
"""

from lib.database.connection import DatabaseConnection

from lib.database.base import DatabaseObject


class WorkflowsTable(DatabaseObject):

    NAME = "workflows"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,

                workflow        TEXT NOT NULL,

                started_at      TEXT NOT NULL,

                finished_at     TEXT,

                duration_ms     INTEGER,

                status          TEXT NOT NULL
            )
            """
        )
