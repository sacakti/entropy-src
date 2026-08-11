"""
Create the Entropy Vault table.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.objects.workflow_registry import WorkflowRegistryTable
from lib.migrations.base import BaseMigration


class VaultMigration(BaseMigration):
    """
    Create the workflow definitions table.
    """

    VERSION = 2

    DESCRIPTION = "Create Entropy workflow definitions table."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the Vault table.
        """

        WorkflowRegistryTable().create(
            connection,
        )
