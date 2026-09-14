"""
Group repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.authorization.exceptions import GroupNotFoundError
from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.models.authorization import Group


class GroupRepository(Repository):
    """
    Repository for authorization groups.
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
        group: Group,
    ) -> Group:
        """
        Create a group.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO groups
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
                    group.name,
                    group.description,
                ),
            )

            group.id = cursor.lastrowid

        assert group.id is not None

        return self.get(
            group.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        group_id: int,
    ) -> Group:
        """
        Return a group by identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM groups
            WHERE id = ?
            """,
            (group_id,),
        )

        if row is None:

            raise GroupNotFoundError(
                group_id,
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
    ) -> Group:
        """
        Return a group by name.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM groups
            WHERE name = ?
            """,
            (name,),
        )

        if row is None:

            raise GroupNotFoundError(
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
        Return True when a group exists.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM groups
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
    ) -> list[Group]:
        """
        Return all groups.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM groups
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
        group: Group,
    ) -> None:
        """
        Update a group.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE groups
                SET
                    name = ?,
                    description = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    group.name,
                    group.description,
                    group.id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        group_id: int,
    ) -> None:
        """
        Delete a group.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM groups
                WHERE id = ?
                """,
                (group_id,),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> Group:
        """
        Convert a database row into a Group.
        """

        return Group(
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
