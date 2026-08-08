"""
Extension registry table.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class WorkflowJobsTable(DatabaseObject):
    """
    Stores workflow jobs.
    """

    NAME = "workflow_jobs"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE workflow_jobs
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                execution_id TEXT NOT NULL UNIQUE,

                workflow TEXT NOT NULL,

                state TEXT NOT NULL,

                pid INTEGER,

                workspace TEXT NOT NULL,

                created_at TEXT NOT NULL,

                started_at TEXT,

                finished_at TEXT,

                exit_code INTEGER
            );
            """
        )
