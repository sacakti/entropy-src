"""Store the inputs and workflow definition needed to repeat a run."""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.objects.runs import create_run_tables
from lib.migrations.base import BaseMigration


class RunRerunConfigMigration(BaseMigration):
    """Add private rerun configuration to live and archived run metadata."""

    VERSION = 13

    DESCRIPTION = "Store workflow input configuration for Run again."

    def upgrade(self, connection: DatabaseConnection) -> None:
        create_run_tables(connection)
