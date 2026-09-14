"""
Group role repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.repository import Repository
from lib.models.authorization import GroupRole, Role


class GroupRoleRepository(Repository):
    """
    Repository for group-to-role assignments.
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
        assignment: GroupRole,
    ) -> GroupRole:
        """
        Assign a role to a group.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO group_roles
                (
                    group_id,
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
                    assignment.group_id,
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
    ) -> GroupRole:
        """
        Return a group-role assignment.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM group_roles
            WHERE id = ?
            """,
            (assignment_id,),
        )

        if row is None:

            raise DatabaseException(
                f"Group role '{assignment_id}' not found.",
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        group_id: int,
        role_id: int,
    ) -> bool:
        """
        Return True when a role is already assigned to a group.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM group_roles
                WHERE group_id = ?
                  AND role_id = ?
                LIMIT 1
                """,
                (
                    group_id,
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
    ) -> list[GroupRole]:
        """
        Return all group-role assignments.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM group_roles
            ORDER BY group_id,
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
    # List by group
    # ------------------------------------------------------------------

    def list_by_group(
        self,
        group_id: int,
    ) -> list[GroupRole]:
        """
        Return roles assigned to a group.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM group_roles
            WHERE group_id = ?
            ORDER BY role_id
            """,
            (group_id,),
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
        group_id: int,
    ) -> list[Role]:
        """
        Return role definitions assigned to a group.
        """

        rows = self.connection.fetchall(
            """
            SELECT
                roles.*
            FROM group_roles
            INNER JOIN roles
                ON roles.id = group_roles.role_id
            WHERE group_roles.group_id = ?
            ORDER BY roles.name
            """,
            (group_id,),
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
        Remove a role from a group.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM group_roles
                WHERE id = ?
                """,
                (assignment_id,),
            )

    # ------------------------------------------------------------------
    # Delete by role
    # ------------------------------------------------------------------

    def delete_by_role(
        self,
        group_id: int,
        role_id: int,
    ) -> None:
        """
        Remove a specific role from a group.

        Removing a missing membership is harmless.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM group_roles
                WHERE group_id = ?
                AND role_id = ?
                """,
                (
                    group_id,
                    role_id,
                ),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> GroupRole:
        """
        Convert a database row into a GroupRole.
        """

        return GroupRole(
            id=row["id"],
            group_id=row["group_id"],
            role_id=row["role_id"],
            created_at=(
                datetime.fromisoformat(
                    row["created_at"],
                )
                if row["created_at"]
                else None
            ),
        )
