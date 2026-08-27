"""
User privilege repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.repository import Repository
from lib.models.authorization import (
    Permission,
    PermissionType,
    UserPrivilege,
)


class UserPrivilegeRepository(Repository):
    """
    Repository for direct user permission assignments.
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
        privilege: UserPrivilege,
    ) -> UserPrivilege:
        """
        Grant a permission directly to a user.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO user_privileges
                (
                    user_id,
                    permission_id,
                    created_at
                )
                VALUES
                (
                    ?,
                    ?,
                    datetime('now')
                )
                """,
                (
                    privilege.user_id,
                    privilege.permission_id,
                ),
            )

            privilege.id = cursor.lastrowid

        assert privilege.id is not None

        return self.get(
            privilege.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        privilege_id: int,
    ) -> UserPrivilege:
        """
        Return a user privilege.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM user_privileges
            WHERE id = ?
            """,
            (
                privilege_id,
            ),
        )

        if row is None:

            raise DatabaseException(
                f"User privilege '{privilege_id}' not found.",
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        user_id: int,
        permission_id: int,
    ) -> bool:
        """
        Return True when the user already has the permission.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM user_privileges
                WHERE user_id = ?
                  AND permission_id = ?
                LIMIT 1
                """,
                (
                    user_id,
                    permission_id,
                ),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[UserPrivilege]:
        """
        Return all user privileges.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM user_privileges
            ORDER BY user_id,
                     permission_id
            """
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
    ) -> list[UserPrivilege]:
        """
        Return direct privileges assigned to a user.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM user_privileges
            WHERE user_id = ?
            ORDER BY permission_id
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
    # List permissions
    # ------------------------------------------------------------------

    def list_permissions(
        self,
        user_id: int,
    ) -> list[Permission]:
        """
        Return permission definitions granted directly to a user.
        """

        rows = self.connection.fetchall(
            """
            SELECT
                permissions.*
            FROM user_privileges
            INNER JOIN permissions
                ON permissions.id = user_privileges.permission_id
            WHERE user_privileges.user_id = ?
            ORDER BY permissions.name
            """,
            (
                user_id,
            ),
        )

        return [
            Permission(
                id=row["id"],
                module_id=row["module_id"],
                name=row["name"],
                description=row["description"],
                permission_type=PermissionType(
                    row["permission_type"],
                ),
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        privilege_id: int,
    ) -> None:
        """
        Remove a direct user privilege.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM user_privileges
                WHERE id = ?
                """,
                (
                    privilege_id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete by permission
    # ------------------------------------------------------------------

    def delete_permission(
        self,
        user_id: int,
        permission_id: int,
    ) -> None:
        """
        Remove a specific direct permission from a user.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM user_privileges
                WHERE user_id = ?
                  AND permission_id = ?
                """,
                (
                    user_id,
                    permission_id,
                ),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> UserPrivilege:
        """
        Convert a database row into a UserPrivilege.
        """

        return UserPrivilege(
            id=row["id"],
            user_id=row["user_id"],
            permission_id=row["permission_id"],
            created_at=(
                datetime.fromisoformat(
                    row["created_at"],
                )
                if row["created_at"]
                else None
            ),
        )
