"""
Add run orchestration: run metadata, nodes, schedules and archives.
"""

from __future__ import annotations

from lib.authorization.initializer import AuthorizationInitializer
from lib.database.connection import DatabaseConnection
from lib.database.objects.runs import create_run_tables
from lib.migrations.base import BaseMigration


class RunsMigration(BaseMigration):
    """
    Store where runs execute, execution nodes, schedules and archives.
    """

    VERSION = 9

    DESCRIPTION = "Add run orchestration, nodes and schedules."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """Create the tables and seed the new node and schedule permissions."""

        create_run_tables(connection)

        AuthorizationInitializer(connection).reconcile()
