"""
Vault repository.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository

from lib.models.vault import VaultEntry, VaultValueType


class VaultRepository(Repository):
    """
    Repository for Vault entries.

    The repository persists the database representation of a
    Vault entry. Encryption and serialization are handled by
    the Vault service layer.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        super().__init__(
            connection,
        )

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        entry: VaultEntry,
    ) -> VaultEntry:
        """
        Create a Vault entry.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO vault_entries
                (
                    key,
                    value,
                    type,
                    sensitive,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?,
                    datetime('now'),
                    datetime('now')
                )
                """,
                (
                    entry.key,
                    entry.value,
                    entry.type.value,
                    int(entry.sensitive),
                ),
            )

            entry.id = cursor.lastrowid

        return self.get_by_key(
            entry.key,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        entry_id: int,
    ) -> Optional[VaultEntry]:
        """
        Return a Vault entry by identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM vault_entries
            WHERE id = ?
            """,
            (entry_id,),
        )

        if row is None:

            return None

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Get by key
    # ------------------------------------------------------------------

    def get_by_key(
        self,
        key: str,
    ) -> Optional[VaultEntry]:
        """
        Return a Vault entry by key.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM vault_entries
            WHERE key = ?
            """,
            (key,),
        )

        if row is None:

            return None

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        key: str,
    ) -> bool:
        """
        Return True if a Vault key exists.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM vault_entries
                WHERE key = ?
                LIMIT 1
                """,
                (key,),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[VaultEntry]:
        """
        Return all Vault entries.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM vault_entries
            ORDER BY key
            """
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        entry: VaultEntry,
    ) -> None:
        """
        Update an existing Vault entry.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE vault_entries
                SET
                    value = ?,
                    type = ?,
                    sensitive = ?,
                    updated_at = datetime('now')
                WHERE key = ?
                """,
                (
                    entry.value,
                    entry.type.value,
                    int(entry.sensitive),
                    entry.key,
                ),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        key: str,
    ) -> None:
        """
        Delete a Vault entry by key.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM vault_entries
                WHERE key = ?
                """,
                (key,),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> VaultEntry:
        """
        Convert a database row into a Vault entry.
        """

        return VaultEntry(
            id=int(
                row["id"],
            ),
            key=row["key"],
            value=row["value"],
            type=VaultValueType(
                row["type"],
            ),
            sensitive=bool(
                row["sensitive"],
            ),
            created_at=(
                datetime.fromisoformat(
                    row["created_at"],
                )
                if row["created_at"]
                else None
            ),
            updated_at=(
                datetime.fromisoformat(
                    row["updated_at"],
                )
                if row["updated_at"]
                else None
            ),
        )
