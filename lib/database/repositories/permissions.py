"""
Permission repository.
"""

from __future__ import annotations

from lib.authorization.exceptions import PermissionNotFoundError
from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.repository import Repository
from lib.models.authorization import Permission, PermissionType


class PermissionRepository(Repository):
    """
    Repository for authorization permissions.
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
        permission: Permission,
    ) -> Permission:
        """
        Create an authorization permission.
        """

        if permission.module_id is None:

            raise DatabaseException(
                "Permission module identifier is required.",
            )

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO permissions
                (
                    module_id,
                    name,
                    description,
                    permission_type
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    permission.module_id,
                    permission.name,
                    permission.description,
                    permission.permission_type.value,
                ),
            )

            permission.id = cursor.lastrowid

        assert permission.id is not None

        return self.get(
            permission.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        permission_id: int,
    ) -> Permission:
        """
        Return a permission by identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM permissions
            WHERE id = ?
            """,
            (permission_id,),
        )

        if row is None:

            raise PermissionNotFoundError(
                permission_id,
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
    ) -> Permission:
        """
        Return a permission by name.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM permissions
            WHERE name = ?
            """,
            (name,),
        )

        if row is None:

            raise PermissionNotFoundError(
                name,
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Get by module
    # ------------------------------------------------------------------

    def list_by_module(
        self,
        module_id: int,
    ) -> list[Permission]:
        """
        Return permissions belonging to a module.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM permissions
            WHERE module_id = ?
            ORDER BY name
            """,
            (module_id,),
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[Permission]:
        """
        Return all authorization permissions.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM permissions
            ORDER BY name
            """
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
        name: str,
    ) -> bool:
        """
        Return True if a permission exists.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM permissions
                WHERE name = ?
                LIMIT 1
                """,
                (name,),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        permission: Permission,
    ) -> None:
        """
        Update an authorization permission.
        """

        if permission.module_id is None:

            raise DatabaseException(
                "Permission module identifier is required.",
            )

        with self.connection.transaction():

            self.execute(
                """
                UPDATE permissions
                SET
                    module_id = ?,
                    name = ?,
                    description = ?,
                    permission_type = ?
                WHERE id = ?
                """,
                (
                    permission.module_id,
                    permission.name,
                    permission.description,
                    permission.permission_type.value,
                    permission.id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        permission_id: int,
    ) -> None:
        """
        Delete an authorization permission.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM permissions
                WHERE id = ?
                """,
                (permission_id,),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> Permission:
        """
        Convert a database row into a Permission.
        """

        return Permission(
            id=row["id"],
            module_id=row["module_id"],
            name=row["name"],
            description=row["description"],
            permission_type=PermissionType(
                row["permission_type"],
            ),
        )
