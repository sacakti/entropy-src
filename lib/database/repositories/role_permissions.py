"""
Role permission repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.repository import Repository
from lib.models.authorization import Permission, PermissionType, RolePermission


class RolePermissionRepository(Repository):
    """
    Repository for role-to-permission assignments.
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
        assignment: RolePermission,
    ) -> RolePermission:
        """
        Assign a permission to a role.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO role_permissions
                (
                    role_id,
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
                    assignment.role_id,
                    assignment.permission_id,
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
    ) -> RolePermission:
        """
        Return a role-permission assignment.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM role_permissions
            WHERE id = ?
            """,
            (assignment_id,),
        )

        if row is None:

            raise DatabaseException(
                f"Role permission '{assignment_id}' not found.",
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        role_id: int,
        permission_id: int,
    ) -> bool:
        """
        Return True when a permission is already assigned to a role.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM role_permissions
                WHERE role_id = ?
                  AND permission_id = ?
                LIMIT 1
                """,
                (
                    role_id,
                    permission_id,
                ),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List by role
    # ------------------------------------------------------------------

    def list_by_role(
        self,
        role_id: int,
    ) -> list[RolePermission]:
        """
        Return permissions assigned to a role.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM role_permissions
            WHERE role_id = ?
            ORDER BY permission_id
            """,
            (role_id,),
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
        role_id: int,
    ) -> list[Permission]:
        """
        Return the permission definitions assigned to a role.
        """

        rows = self.connection.fetchall(
            """
            SELECT
                permissions.*
            FROM role_permissions
            INNER JOIN permissions
                ON permissions.id = role_permissions.permission_id
            WHERE role_permissions.role_id = ?
            ORDER BY permissions.name
            """,
            (role_id,),
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
        assignment_id: int,
    ) -> None:
        """
        Remove a permission from a role.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM role_permissions
                WHERE id = ?
                """,
                (assignment_id,),
            )

    # ------------------------------------------------------------------
    # Delete by permission
    # ------------------------------------------------------------------

    def delete_permission(
        self,
        role_id: int,
        permission_id: int,
    ) -> None:
        """
        Remove a specific permission from a role.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM role_permissions
                WHERE role_id = ?
                  AND permission_id = ?
                """,
                (
                    role_id,
                    permission_id,
                ),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> RolePermission:
        """
        Convert a database row into a RolePermission.
        """

        return RolePermission(
            id=row["id"],
            role_id=row["role_id"],
            permission_id=row["permission_id"],
            created_at=(
                datetime.fromisoformat(
                    row["created_at"],
                )
                if row["created_at"]
                else None
            ),
        )
