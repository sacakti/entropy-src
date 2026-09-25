"""
Add workflow job execution identity.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class WorkflowJobIdentityMigration(BaseMigration):
    """
    Add execution identity to workflow jobs.
    """

    VERSION = 4

    DESCRIPTION = "Add workflow job execution identity."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Add user identity columns to workflow jobs.
        """

        connection.execute(
            """
            ALTER TABLE workflow_jobs
            ADD COLUMN user_id INTEGER;
            """
        )

        connection.execute(
            """
            ALTER TABLE workflow_jobs
            ADD COLUMN username TEXT;
            """
        )
