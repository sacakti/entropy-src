"""
Vault namespace access repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.models.authorization import (
    VaultAccess,
    VaultNamespaceAccess,
)


class VaultNamespaceAccessRepository(Repository):
    """
    Repository for Vault namespace access assignments.
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
        assignment: VaultNamespaceAccess,
    ) -> VaultNamespaceAccess:
        """
        Grant access to a Vault namespace.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO vault_namespace_access
                (
                    namespace_id,
                    user_id,
                    access,
                    created_at
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    datetime('now')
                )
                """,
                (
                    assignment.namespace_id,
                    assignment.user_id,
                    assignment.access.value,
                ),
            )

            assignment.id = cursor.lastrowid

        assert assignment.id is not None

        return self.get(
            assignment.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        assignment_id: int,
    ) -> VaultNamespaceAccess:
        """
        Return an access assignment by identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM vault_namespace_access
            WHERE id = ?
            """,
            (
                assignment_id,
            ),
        )

        if row is None:

            raise ValueError(
                f"Vault namespace access '{assignment_id}' not found.",
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        namespace_id: int,
        user_id: int,
    ) -> bool:
        """
        Return True when a user already has namespace access.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM vault_namespace_access
                WHERE namespace_id = ?
                  AND user_id = ?
                LIMIT 1
                """,
                (
                    namespace_id,
                    user_id,
                ),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # Get access
    # ------------------------------------------------------------------

    def get_access(
        self,
        namespace_id: int,
        user_id: int,
    ) -> VaultAccess | None:
        """
        Return the access level assigned to a user.
        """

        row = self.connection.fetchone(
            """
            SELECT access
            FROM vault_namespace_access
            WHERE namespace_id = ?
              AND user_id = ?
            """,
            (
                namespace_id,
                user_id,
            ),
        )

        if row is None:

            return None

        return VaultAccess(
            row["access"],
        )

    # ------------------------------------------------------------------
    # List by namespace
    # ------------------------------------------------------------------

    def list_by_namespace(
        self,
        namespace_id: int,
    ) -> list[VaultNamespaceAccess]:
        """
        Return all access assignments for a namespace.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM vault_namespace_access
            WHERE namespace_id = ?
            ORDER BY user_id
            """,
            (
                namespace_id,
            ),
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # List by user
    # ------------------------------------------------------------------

    def list_by_user(
        self,
        user_id: int,
    ) -> list[VaultNamespaceAccess]:
        """
        Return all namespace assignments for a user.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM vault_namespace_access
            WHERE user_id = ?
            ORDER BY namespace_id
            """,
            (
                user_id,
            ),
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Update access
    # ------------------------------------------------------------------

    def update_access(
        self,
        namespace_id: int,
        user_id: int,
        access: VaultAccess,
    ) -> None:
        """
        Update an existing namespace access level.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE vault_namespace_access
                SET access = ?
                WHERE namespace_id = ?
                  AND user_id = ?
                """,
                (
                    access.value,
                    namespace_id,
                    user_id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        assignment_id: int,
    ) -> None:
        """
        Remove a namespace access assignment.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM vault_namespace_access
                WHERE id = ?
                """,
                (
                    assignment_id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete by user
    # ------------------------------------------------------------------

    def delete_by_user(
        self,
        namespace_id: int,
        user_id: int,
    ) -> None:
        """
        Remove a user's access to a namespace.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM vault_namespace_access
                WHERE namespace_id = ?
                  AND user_id = ?
                """,
                (
                    namespace_id,
                    user_id,
                ),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> VaultNamespaceAccess:
        """
        Convert a database row into a namespace access assignment.
        """

        return VaultNamespaceAccess(
            id=row["id"],
            namespace_id=row["namespace_id"],
            user_id=row["user_id"],
            access=VaultAccess(
                row["access"],
            ),
            created_at=(
                datetime.fromisoformat(
                    row["created_at"],
                )
                if row["created_at"]
                else None
            ),
        )
