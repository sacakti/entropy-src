"""
User group repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.exceptions import DatabaseException
from lib.database.repository import Repository
from lib.models.authorization import Group, UserGroup
from lib.models.users import User


class UserGroupRepository(Repository):
    """
    Repository for user-to-group assignments.
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
        assignment: UserGroup,
    ) -> UserGroup:
        """
        Add a user to a group.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO user_groups
                (
                    user_id,
                    group_id,
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
                    assignment.group_id,
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
    ) -> UserGroup:
        """
        Return a user-group assignment.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM user_groups
            WHERE id = ?
            """,
            (
                assignment_id,
            ),
        )

        if row is None:

            raise DatabaseException(
                f"User group '{assignment_id}' not found.",
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
        group_id: int,
    ) -> bool:
        """
        Return True when a user already belongs to a group.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM user_groups
                WHERE user_id = ?
                  AND group_id = ?
                LIMIT 1
                """,
                (
                    user_id,
                    group_id,
                ),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[UserGroup]:
        """
        Return all user-group assignments.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM user_groups
            ORDER BY user_id,
                     group_id
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
    ) -> list[UserGroup]:
        """
        Return groups assigned to a user.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM user_groups
            WHERE user_id = ?
            ORDER BY group_id
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
    # List groups
    # ------------------------------------------------------------------

    def list_groups(
        self,
        user_id: int,
    ) -> list[Group]:
        """
        Return group definitions assigned to a user.
        """

        rows = self.connection.fetchall(
            """
            SELECT
                groups.*
            FROM user_groups
            INNER JOIN groups
                ON groups.id = user_groups.group_id
            WHERE user_groups.user_id = ?
            ORDER BY groups.name
            """,
            (
                user_id,
            ),
        )

        return [
            Group(
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
        Remove a user from a group.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM user_groups
                WHERE id = ?
                """,
                (
                    assignment_id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete by group
    # ------------------------------------------------------------------

    def delete_group(
        self,
        user_id: int,
        group_id: int,
    ) -> None:
        """
        Remove a specific group from a user.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM user_groups
                WHERE user_id = ?
                  AND group_id = ?
                """,
                (
                    user_id,
                    group_id,
                ),
            )
    # ------------------------------------------------------------------
    # List users
    # ------------------------------------------------------------------

    def list_users(
        self,
        group_id: int,
    ) -> list[User]:
        """
        Return users belonging to a group.
        """

        rows = self.connection.fetchall(
            """
            SELECT
                users.*
            FROM user_groups
            INNER JOIN users
                ON users.id = user_groups.user_id
            WHERE user_groups.group_id = ?
            ORDER BY users.username
            """,
            (
                group_id,
            ),
        )

        return [
            User(
                id=row["id"],
                username=row["username"],
                password_hash=row["password_hash"],
                full_name=row["full_name"],
                email=row["email"],
                is_active=bool(
                    row["is_active"],
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
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> UserGroup:
        """
        Convert a database row into a UserGroup.
        """

        return UserGroup(
            id=row["id"],
            user_id=row["user_id"],
            group_id=row["group_id"],
            created_at=(
                datetime.fromisoformat(
                    row["created_at"],
                )
                if row["created_at"]
                else None
            ),
        )
