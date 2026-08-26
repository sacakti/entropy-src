"""
Vault namespaces database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class VaultNamespacesTable(DatabaseObject):
    """
    Stores Entropy Vault namespaces.
    """

    NAME = "vault_namespaces"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the Vault namespaces table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS vault_namespaces
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL UNIQUE,

                owner_user_id INTEGER NOT NULL,

                visibility TEXT NOT NULL,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL,

                FOREIGN KEY (
                    owner_user_id
                )
                REFERENCES users (
                    id
                )
                ON DELETE RESTRICT
            )
            """
        )
