"""
Add workflow job display name.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class WorkflowJobDisplayNameMigration(BaseMigration):
    """
    Add the execution user's display name to workflow jobs.
    """

    VERSION = 5

    DESCRIPTION = "Add workflow job display name."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Add the user's display name to workflow jobs.
        """

        connection.execute(
            """
            ALTER TABLE workflow_jobs
            ADD COLUMN full_name TEXT;
            """
        )
