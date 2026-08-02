"""
User repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.models.users import User
from lib.users.exceptions import UserNotFoundError


class UserRepository(Repository):
    """
    User repository.
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
        user: User,
    ) -> User:
        """
        Create a user.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO users
                (
                    username,
                    password_hash,
                    full_name,
                    email,
                    group_id,
                    system,
                    is_active,
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
                    ?,
                    ?,
                    datetime('now'),
                    datetime('now')
                )
                """,
                (
                    user.username,
                    user.password_hash,
                    user.full_name,
                    user.email,
                    user.group_id,
                    int(user.system),
                    int(user.is_active),
                ),
            )

            user.id = cursor.lastrowid

        assert user.id is not None

        return self.get(
            user.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        user_id: int,
    ) -> User:
        """
        Return a user by identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )

        if row is None:

            raise UserNotFoundError(
                str(user_id),
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Get by Username
    # ------------------------------------------------------------------

    def get_by_username(
        self,
        username: str,
    ) -> User:
        """
        Return a user by username.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,),
        )

        if row is None:

            raise UserNotFoundError(
                username,
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        username: str,
    ) -> bool:
        """
        Return True if the user exists.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM users
                WHERE username = ?
                LIMIT 1
                """,
                (username,),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[User]:
        """
        Return all users.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM users
            ORDER BY username
            """
        )

        return [self._from_row(row) for row in rows]

    # ------------------------------------------------------------------
    # Any
    # ------------------------------------------------------------------

    def any(
        self,
    ) -> bool:
        """
        Return True if any users exist.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM users
                LIMIT 1
                """
            )
            is not None
        )

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def count(
        self,
    ) -> int:
        """
        Return the number of users.
        """

        row = self.connection.fetchone(
            """
            SELECT COUNT(*)
            FROM users
            """
        )

        assert row is not None

        return int(
            row[0],
        )

    # ------------------------------------------------------------------
    # System User
    # ------------------------------------------------------------------

    def system_user(
        self,
    ) -> User:
        """
        Return the bootstrap system user.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM users
            WHERE system = 1
            LIMIT 1
            """
        )

        if row is None:

            raise UserNotFoundError(
                "system",
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        user: User,
    ) -> None:
        """
        Update a user.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE users
                SET
                    password_hash = ?,
                    full_name = ?,
                    email = ?,
                    group_id = ?,
                    system = ?,
                    is_active = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    user.password_hash,
                    user.full_name,
                    user.email,
                    user.group_id,
                    int(user.system),
                    int(user.is_active),
                    user.id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        user_id: int,
    ) -> None:
        """
        Delete a user.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> User:
        """
        Convert a database row into a User.
        """

        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            full_name=row["full_name"],
            email=row["email"],
            group_id=row["group_id"],
            system=bool(row["system"]),
            is_active=bool(row["is_active"]),
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
