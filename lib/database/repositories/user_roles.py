"""
User role repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.repository import Repository
from lib.models.authorization import Role, UserRole


class UserRoleRepository(Repository):
    """
    Repository for user-to-role assignments.
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
        assignment: UserRole,
    ) -> UserRole:
        """
        Assign a role to a user.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO user_roles
                (
                    user_id,
                    role_id,
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
                    assignment.user_id,
                    assignment.role_id,
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
    ) -> UserRole:
        """
        Return a user-role assignment.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM user_roles
            WHERE id = ?
            """,
            (assignment_id,),
        )

        if row is None:

            raise DatabaseException(
                f"User role '{assignment_id}' not found.",
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
        role_id: int,
    ) -> bool:
        """
        Return True when the user already has the role.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM user_roles
                WHERE user_id = ?
                  AND role_id = ?
                LIMIT 1
                """,
                (
                    user_id,
                    role_id,
                ),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[UserRole]:
        """
        Return all user-role assignments.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM user_roles
            ORDER BY user_id,
                     role_id
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
    ) -> list[UserRole]:
        """
        Return roles assigned to a user.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM user_roles
            WHERE user_id = ?
            ORDER BY role_id
            """,
            (user_id,),
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # List roles
    # ------------------------------------------------------------------

    def list_roles(
        self,
        user_id: int,
    ) -> list[Role]:
        """
        Return role definitions assigned to a user.
        """

        rows = self.connection.fetchall(
            """
            SELECT
                roles.*
            FROM user_roles
            INNER JOIN roles
                ON roles.id = user_roles.role_id
            WHERE user_roles.user_id = ?
            ORDER BY roles.name
            """,
            (user_id,),
        )

        return [
            Role(
                id=row["id"],
                name=row["name"],
                description=row["description"],
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
        Remove a role from a user.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM user_roles
                WHERE id = ?
                """,
                (assignment_id,),
            )

    # ------------------------------------------------------------------
    # Delete by role
    # ------------------------------------------------------------------

    def delete_role(
        self,
        user_id: int,
        role_id: int,
    ) -> None:
        """
        Remove a specific role from a user.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM user_roles
                WHERE user_id = ?
                  AND role_id = ?
                """,
                (
                    user_id,
                    role_id,
                ),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> UserRole:
        """
        Convert a database row into a UserRole.
        """

        return UserRole(
            id=row["id"],
            user_id=row["user_id"],
            role_id=row["role_id"],
            created_at=(
                datetime.fromisoformat(
                    row["created_at"],
                )
                if row["created_at"]
                else None
            ),
        )
