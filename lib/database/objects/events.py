"""
Extension registry table.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class WorkflowEventsTable(DatabaseObject):
    """
    Stores workflow events.
    """

    NAME = "workflow_events"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE workflow_events
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                job_id INTEGER NOT NULL,

                execution_id TEXT NOT NULL,

                event_type TEXT NOT NULL,

                source TEXT,

                level TEXT,

                message TEXT,

                node_type TEXT,

                node_id TEXT,

                node_name TEXT,

                payload TEXT,

                created_at TEXT NOT NULL,

                FOREIGN KEY (
                    job_id
                )
                REFERENCES workflow_jobs (
                    id
                )
                ON DELETE CASCADE
            );
            """
        )
