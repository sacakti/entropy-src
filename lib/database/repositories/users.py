"""
User repository.
"""

from datetime import datetime

from lib.models.users import User


class UserRepository:

    def __init__(self, connection):

        self._connection = connection

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        user: User,
    ) -> User:

        cursor = self._connection.connection.execute(
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

        self._connection.connection.commit()

        user.id = cursor.lastrowid

        return self.get(user.id)

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        user_id: int,
    ) -> User:

        cursor = self._connection.connection.execute(
            """
            SELECT *
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )

        return self._map(cursor.fetchone())

    # ------------------------------------------------------------------
    # Get by username
    # ------------------------------------------------------------------

    def get_by_username(
        self,
        username: str,
    ) -> User:

        cursor = self._connection.connection.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,),
        )

        return self._map(cursor.fetchone())

    def exists(
        self,
        username: str,
    ) -> bool:

        cursor = self._connection.connection.execute(
            """
            SELECT 1
            FROM users
            WHERE username = ?
            LIMIT 1
            """,
            (username,),
        )

        return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(self) -> list[User]:

        cursor = self._connection.connection.execute(
            """
            SELECT *
            FROM users
            ORDER BY username
            """
        )

        return [self._map(row) for row in cursor.fetchall()]

    def any(self) -> bool:

        cursor = self._connection.connection.execute(
            """
            SELECT 1
            FROM users
            LIMIT 1
            """
        )

        return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        user: User,
    ):

        self._connection.connection.execute(
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

        self._connection.connection.commit()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        user_id: int,
    ):

        self._connection.connection.execute(
            """
            DELETE
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )

        self._connection.connection.commit()

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    def _map(
        self,
        row,
    ) -> User:

        if row is None:
            return None

        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            full_name=row["full_name"],
            email=row["email"],
            group_id=row["group_id"],
            system=bool(row["system"]),
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    def count(self) -> int:

        cursor = self._connection.connection.execute(
            """
            SELECT COUNT(*)
            FROM users
            """
        )

        return cursor.fetchone()[0]

    def system_user(self) -> User:

        cursor = self._connection.connection.execute(
            """
            SELECT *
            FROM users
            WHERE system = 1
            LIMIT 1
            """
        )

        return self._map(cursor.fetchone())
