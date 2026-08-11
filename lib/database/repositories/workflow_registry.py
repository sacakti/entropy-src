"""
Workflow definition repository.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterator

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.models.workflow_registry import WorkflowRegistryEntry


class WorkflowRegistryRepository(Repository):
    """
    Persistence repository for registered workflows.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        super().__init__(
            connection,
        )

    # ------------------------------------------------------------------
    # Transaction
    # ------------------------------------------------------------------

    def transaction(self):
        """
        Return a database transaction context.
        """

        return self._connection.transaction()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        version: str,
        description: str | None,
        definition: str,
        created_at: str,
        updated_at: str,
    ) -> WorkflowRegistryEntry:
        """
        Create a workflow registry entry.
        """

        with self.transaction():
            self.execute(
                """
                INSERT INTO workflow_registry
                (
                    name,
                    version,
                    description,
                    definition,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    version,
                    description,
                    definition,
                    created_at,
                    updated_at,
                ),
            )

            # result = self.get_by_name(
            #     name,
            # )

        result = self.get_by_name(
            name,
        )

        if result is None:

            raise RuntimeError(
                f"Unable to load newly created workflow '{name}'.",
            )

        return result

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get_by_name(
        self,
        name: str,
    ) -> WorkflowRegistryEntry | None:
        """
        Return a registered workflow by name.
        """
        with self.transaction():
            cursor = self.execute(
                """
                SELECT
                    id,
                    name,
                    version,
                    description,
                    definition,
                    created_at,
                    updated_at
                FROM workflow_registry
                WHERE name = ?
                """,
                (
                    name,
                ),
            )

        row = cursor.fetchone()

        if row is None:
            return None

        return self._model(
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
        Return whether a workflow exists.
        """

        with self.transaction():
            cursor = self.execute(
                """
                SELECT 1
                FROM workflow_registry
                WHERE name = ?
                LIMIT 1
                """,
                (
                    name,
                ),
            )

        return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[WorkflowRegistryEntry]:
        """
        Return registered workflows.
        """

        with self.transaction():
            cursor = self.execute(
                """
                SELECT
                    id,
                    name,
                    version,
                    description,
                    definition,
                    created_at,
                    updated_at
                FROM workflow_registry
                ORDER BY name
                """,
            )

        return [
            self._model(
                row,
            )
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        name: str,
        version: str,
        description: str | None,
        definition: str,
        updated_at: str,
    ) -> WorkflowRegistryEntry:
        """
        Replace an existing workflow definition.
        """

        with self.transaction():
            cursor = self.execute(
                """
                UPDATE workflow_registry
                SET
                    version = ?,
                    description = ?,
                    definition = ?,
                    updated_at = ?
                WHERE name = ?
                """,
                (
                    version,
                    description,
                    definition,
                    updated_at,
                    name,
                ),
            )

        if cursor.rowcount == 0:

            raise KeyError(
                f"Workflow '{name}' does not exist.",
            )

        result = self.get_by_name(
            name,
        )

        if result is None:

            raise RuntimeError(
                f"Unable to load updated workflow '{name}'.",
            )

        return result

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        name: str,
    ) -> None:
        """
        Remove a registered workflow.
        """

        with self.transaction():
            cursor = self.execute(
                """
                DELETE FROM workflow_registry
                WHERE name = ?
                """,
                (
                    name,
                ),
            )

        if cursor.rowcount == 0:

            raise KeyError(
                f"Workflow '{name}' does not exist.",
            )

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------

    @staticmethod
    def _model(
        row,
    ) -> WorkflowRegistryEntry:
        """
        Convert a database row into a model.
        """

        return WorkflowRegistryEntry(
            id=int(
                row["id"],
            ),
            name=row["name"],
            version=row["version"],
            description=row["description"],
            definition=row["definition"],
            created_at=datetime.fromisoformat(
                row["created_at"],
            ),
            updated_at=datetime.fromisoformat(
                row["updated_at"],
            ),
        )
