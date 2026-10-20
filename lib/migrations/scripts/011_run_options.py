"""
Record each run's plan (selected steps, tags, node per step) and link the
segments of a run that spans several nodes to that run.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.objects.runs import create_run_tables
from lib.migrations.base import BaseMigration


class RunOptionsMigration(BaseMigration):
    """
    Add run_metadata.options and run_metadata.parent_job_id.
    """

    VERSION = 11

    DESCRIPTION = "Add run options and multi-node run segments."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """Add the run_metadata columns."""

        create_run_tables(connection)
