"""
Create the Entropy Vault table.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.objects.vault import VaultEntriesTable
from lib.migrations.base import BaseMigration


class VaultMigration(BaseMigration):
    """
    Create the Vault entries table.
    """

    VERSION = 1

    DESCRIPTION = "Create Entropy Vault entries table."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the Vault table.
        """

        VaultEntriesTable().create(
            connection,
        )
