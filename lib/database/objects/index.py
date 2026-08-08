"""
Extension registry table.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class Indexes(DatabaseObject):
    """
    Index creation.
    """

    NAME = "indexes"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE INDEX idx_workflow_jobs_state
            ON workflow_jobs (
                state
            );
            CREATE INDEX idx_workflow_events_job
            ON workflow_events (
                job_id,
                id
            );
            CREATE INDEX idx_workflow_events_execution
            ON workflow_events (
                execution_id,
                id
            );
            """
        )
