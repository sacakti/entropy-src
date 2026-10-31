"""
Vault namespaces database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class VaultNamespacesTable(DatabaseObject):
    """
    Stores Entropy Vault namespaces, each owned by a project
    (see migration 026).
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

                -- Namespaces belong to a project; names are unique in it.
                project_id INTEGER NOT NULL,

                name TEXT NOT NULL,

                -- Who created it (informational; access comes from project roles).
                owner_user_id INTEGER
                    REFERENCES users (id) ON DELETE SET NULL,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL,

                UNIQUE (project_id, name)
            )
            """
        )
