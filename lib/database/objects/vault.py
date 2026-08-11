"""
Vault database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class VaultEntriesTable(DatabaseObject):
    """
    Stores Entropy Vault entries.
    """

    NAME = "vault_entries"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the Vault entries table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS vault_entries
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                key TEXT NOT NULL UNIQUE,

                value TEXT NOT NULL,

                type TEXT NOT NULL,

                sensitive INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL
            )
            """
        )
