"""
Module repository.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.models.authorization import Module


class ModuleRepository(Repository):
    """
    Repository for authorization modules.
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
        module: Module,
    ) -> Module:
        """
        Create an authorization module.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO modules
                (
                    name,
                    description
                )
                VALUES
                (
                    ?,
                    ?
                )
                """,
                (
                    module.name,
                    module.description,
                ),
            )

            module.id = cursor.lastrowid

        assert module.id is not None

        return self.get(
            module.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        module_id: int,
    ) -> Module:
        """
        Return a module by identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM modules
            WHERE id = ?
            """,
            (
                module_id,
            ),
        )

        if row is None:

            raise ValueError(
                f"Authorization module '{module_id}' not found.",
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
    ) -> Module:
        """
        Return a module by name.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM modules
            WHERE name = ?
            """,
            (
                name,
            ),
        )

        if row is None:

            raise ValueError(
                f"Authorization module '{name}' not found.",
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
        Return True if a module exists.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM modules
                WHERE name = ?
                LIMIT 1
                """,
                (
                    name,
                ),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[Module]:
        """
        Return all authorization modules.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM modules
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
        module: Module,
    ) -> None:
        """
        Update an authorization module.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE modules
                SET
                    name = ?,
                    description = ?
                WHERE id = ?
                """,
                (
                    module.name,
                    module.description,
                    module.id,
                ),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        module_id: int,
    ) -> None:
        """
        Delete an authorization module.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM modules
                WHERE id = ?
                """,
                (
                    module_id,
                ),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> Module:
        """
        Convert a database row into a Module.
        """

        return Module(
            id=row["id"],
            name=row["name"],
            description=row["description"],
        )
