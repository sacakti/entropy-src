"""
Vault repository.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.models.vault import VaultEntry, VaultValueType
from lib.vault.exceptions import VaultValueError


class VaultRepository(Repository):
    """
    Repository for Vault entries.

    The repository persists the database representation of a
    Vault entry. Encryption and serialization are handled by the
    Vault service layer.
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

        if entry.namespace_id is None:

            raise VaultValueError(
                "Vault namespace is required.",
            )

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO vault_entries
                (
                    namespace_id,
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
                    ?,
                    datetime('now'),
                    datetime('now')
                )
                """,
                (
                    entry.namespace_id,
                    entry.key,
                    entry.value,
                    entry.type.value,
                    int(entry.sensitive),
                ),
            )

            entry.id = cursor.lastrowid

        assert entry.id is not None

        return self.get(
            entry.id,
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
        namespace_id: int,
        key: str,
    ) -> Optional[VaultEntry]:
        """
        Return a Vault entry by key within a namespace.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM vault_entries
            WHERE namespace_id = ?
              AND key = ?
            """,
            (
                namespace_id,
                key,
            ),
        )

        if row is None:

            return None

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Get by prefix
    # ------------------------------------------------------------------

    def get_by_prefix(
        self,
        namespace_id: int,
        prefix: str,
    ) -> list[VaultEntry]:
        """
        Return Vault entries whose keys start with the given prefix
        within a namespace.
        """

        upper_bound = prefix + "\U0010ffff"

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM vault_entries
            WHERE namespace_id = ?
              AND key >= ?
              AND key < ?
            ORDER BY key
            """,
            (
                namespace_id,
                prefix,
                upper_bound,
            ),
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        namespace_id: int,
        key: str,
    ) -> bool:
        """
        Return True if a Vault key exists in a namespace.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM vault_entries
                WHERE namespace_id = ?
                  AND key = ?
                LIMIT 1
                """,
                (
                    namespace_id,
                    key,
                ),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
        namespace_id: int,
    ) -> list[VaultEntry]:
        """
        Return all Vault entries in a namespace.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM vault_entries
            WHERE namespace_id = ?
            ORDER BY key
            """,
            (namespace_id,),
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

        if entry.namespace_id is None:

            raise VaultValueError(
                "Vault namespace is required.",
            )

        with self.connection.transaction():

            self.execute(
                """
                UPDATE vault_entries
                SET
                    value = ?,
                    type = ?,
                    sensitive = ?,
                    updated_at = datetime('now')
                WHERE namespace_id = ?
                  AND key = ?
                """,
                (
                    entry.value,
                    entry.type.value,
                    int(entry.sensitive),
                    entry.namespace_id,
                    entry.key,
                ),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        namespace_id: int,
        key: str,
    ) -> None:
        """
        Delete a Vault entry from a namespace.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM vault_entries
                WHERE namespace_id = ?
                  AND key = ?
                """,
                (
                    namespace_id,
                    key,
                ),
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
            namespace_id=int(
                row["namespace_id"],
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
