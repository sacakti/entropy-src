"""
Vault namespace access database table.
"""

from __future__ import annotations

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class VaultNamespaceAccessTable(DatabaseObject):
    """
    Stores user access to Vault namespaces.
    """

    NAME = "vault_namespace_access"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Create the Vault namespace access table.
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS vault_namespace_access
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                namespace_id INTEGER NOT NULL,

                user_id INTEGER NOT NULL,

                access TEXT NOT NULL,

                created_at TEXT NOT NULL,

                UNIQUE (
                    namespace_id,
                    user_id
                ),

                FOREIGN KEY (
                    namespace_id
                )
                REFERENCES vault_namespaces (
                    id
                )
                ON DELETE CASCADE,

                FOREIGN KEY (
                    user_id
                )
                REFERENCES users (
                    id
                )
                ON DELETE CASCADE
            )
            """
        )
