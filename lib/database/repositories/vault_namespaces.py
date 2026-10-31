"""
Vault namespace repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.repository import Repository
from lib.models.authorization import VaultNamespace
from lib.vault.exceptions import (
    VaultNamespaceExistsError,
    VaultNamespaceNotFoundError,
)


class VaultNamespaceRepository(Repository):
    """
    Repository for Vault namespaces.
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
        namespace: VaultNamespace,
    ) -> VaultNamespace:
        """
        Create a Vault namespace.
        """

        if self.exists(
            namespace.name,
            namespace.project_id,
        ):

            raise VaultNamespaceExistsError(
                namespace.name,
            )

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO vault_namespaces
                (
                    project_id,
                    name,
                    owner_user_id,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    datetime('now'),
                    datetime('now')
                )
                """,
                (
                    namespace.project_id,
                    namespace.name,
                    namespace.owner_user_id,
                ),
            )

            namespace.id = cursor.lastrowid

        assert namespace.id is not None

        return self.get(
            namespace.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        namespace_id: int,
    ) -> VaultNamespace:
        """
        Return a namespace by identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM vault_namespaces
            WHERE id = ?
            """,
            (namespace_id,),
        )

        if row is None:

            raise VaultNamespaceNotFoundError(
                str(namespace_id),
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Get by name
    # ------------------------------------------------------------------

    def get_by_name(
        self,
        name: str,
        project_id: int,
    ) -> VaultNamespace:
        """
        Return a project's namespace by name.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM vault_namespaces
            WHERE project_id = ?
              AND name = ?
            """,
            (project_id, name),
        )

        if row is None:

            raise VaultNamespaceNotFoundError(
                name,
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        name: str,
        project_id: int,
    ) -> bool:
        """
        Return True when a namespace exists.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM vault_namespaces
                WHERE project_id = ?
                  AND name = ?
                LIMIT 1
                """,
                (project_id, name),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
        project_id: int | None = None,
    ) -> list[VaultNamespace]:
        """
        Return Vault namespaces: one project's, or all of them.
        """

        if project_id is None:

            rows = self.connection.fetchall(
                """
                SELECT *
                FROM vault_namespaces
                ORDER BY name
                """
            )

        else:

            rows = self.connection.fetchall(
                """
                SELECT *
                FROM vault_namespaces
                WHERE project_id = ?
                ORDER BY name
                """,
                (project_id,),
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
        namespace: VaultNamespace,
    ) -> None:
        """
        Update a Vault namespace.
        """

        if namespace.id is None:

            raise DatabaseException(
                "Vault namespace identifier is required.",
            )

        with self.connection.transaction():

            self.execute(
                """
                UPDATE vault_namespaces
                SET
                    name = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    namespace.name,
                    namespace.id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        namespace_id: int,
    ) -> None:
        """
        Delete a Vault namespace.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM vault_namespaces
                WHERE id = ?
                """,
                (namespace_id,),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> VaultNamespace:
        """
        Convert a database row into a Vault namespace.
        """

        return VaultNamespace(
            id=row["id"],
            name=row["name"],
            project_id=int(row["project_id"]),
            owner_user_id=row["owner_user_id"],
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
