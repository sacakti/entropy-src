"""
Add remote execution nodes: node job queue, provisioning log and the
columns remote nodes need.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.objects.runs import create_run_tables
from lib.migrations.base import BaseMigration


class RemoteNodesMigration(BaseMigration):
    """
    Store remote node details, dispatched jobs and setup attempts.
    """

    VERSION = 10

    DESCRIPTION = "Add remote execution nodes."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """Create the node tables and add remote-node columns."""

        create_run_tables(connection)
