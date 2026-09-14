"""
Role repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.authorization.exceptions import RoleNotFoundError
from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.models.authorization import Role


class RoleRepository(Repository):
    """
    Repository for authorization roles.
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
        role: Role,
    ) -> Role:
        """
        Create an authorization role.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO roles
                (
                    name,
                    description,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    ?,
                    ?,
                    datetime('now'),
                    datetime('now')
                )
                """,
                (
                    role.name,
                    role.description,
                ),
            )

            role.id = cursor.lastrowid

        assert role.id is not None

        return self.get(
            role.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        role_id: int,
    ) -> Role:
        """
        Return a role by identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM roles
            WHERE id = ?
            """,
            (role_id,),
        )

        if row is None:

            raise RoleNotFoundError(
                role_id,
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
    ) -> Role:
        """
        Return a role by name.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM roles
            WHERE name = ?
            """,
            (name,),
        )

        if row is None:

            raise RoleNotFoundError(
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
    ) -> bool:
        """
        Return True if a role exists.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM roles
                WHERE name = ?
                LIMIT 1
                """,
                (name,),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[Role]:
        """
        Return all roles.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM roles
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
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        role: Role,
    ) -> None:
        """
        Update an authorization role.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE roles
                SET
                    name = ?,
                    description = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    role.name,
                    role.description,
                    role.id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        role_id: int,
    ) -> None:
        """
        Delete an authorization role.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM roles
                WHERE id = ?
                """,
                (role_id,),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> Role:
        """
        Convert a database row into a Role.
        """

        return Role(
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
