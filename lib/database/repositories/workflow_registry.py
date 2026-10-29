"""
Workflow definition repository.
"""

from __future__ import annotations

from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.models.workflow_registry import WorkflowRegistryEntry


class WorkflowRegistryRepository(Repository):
    """
    Persistence repository for registered workflows.

    Workflows are project scoped: every lookup is by (project_id, name).
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
        project_id: int,
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
                    project_id,
                    name,
                    version,
                    description,
                    definition,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    name,
                    version,
                    description,
                    definition,
                    created_at,
                    updated_at,
                ),
            )

        result = self.get_by_name(
            project_id,
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
        project_id: int,
        name: str,
    ) -> WorkflowRegistryEntry | None:
        """
        Return a project's registered workflow by name.
        """
        with self.transaction():
            cursor = self.execute(
                """
                SELECT
                    id,
                    project_id,
                    name,
                    version,
                    description,
                    definition,
                    created_at,
                    updated_at
                FROM workflow_registry
                WHERE project_id = ? AND name = ?
                """,
                (project_id, name),
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
        project_id: int,
        name: str,
    ) -> bool:
        """
        Return whether a project has a workflow with this name.
        """

        with self.transaction():
            cursor = self.execute(
                """
                SELECT 1
                FROM workflow_registry
                WHERE project_id = ? AND name = ?
                LIMIT 1
                """,
                (project_id, name),
            )

        return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
        project_id: int | None = None,
    ) -> list[WorkflowRegistryEntry]:
        """
        Return a project's registered workflows (every project's when
        project_id is None).
        """

        where = "" if project_id is None else "WHERE project_id = ?"

        with self.transaction():
            cursor = self.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    name,
                    version,
                    description,
                    definition,
                    created_at,
                    updated_at
                FROM workflow_registry
                {where}
                ORDER BY name, project_id
                """,
                () if project_id is None else (project_id,),
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
        project_id: int,
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
                WHERE project_id = ? AND name = ?
                """,
                (
                    version,
                    description,
                    definition,
                    updated_at,
                    project_id,
                    name,
                ),
            )

        if cursor.rowcount == 0:

            raise KeyError(
                f"Workflow '{name}' does not exist.",
            )

        result = self.get_by_name(
            project_id,
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
        project_id: int,
        name: str,
    ) -> None:
        """
        Remove a registered workflow.
        """

        with self.transaction():
            cursor = self.execute(
                """
                DELETE FROM workflow_registry
                WHERE project_id = ? AND name = ?
                """,
                (project_id, name),
            )

        if cursor.rowcount == 0:

            raise KeyError(
                f"Workflow '{name}' does not exist.",
            )

    # ------------------------------------------------------------------
    # Move
    # ------------------------------------------------------------------

    def move(
        self,
        name: str,
        source_project_id: int,
        target_project_id: int,
    ) -> None:
        """
        Move a workflow to another project (which must not have one of that name).
        """

        with self.transaction():
            cursor = self.execute(
                """
                UPDATE workflow_registry
                SET project_id = ?
                WHERE project_id = ? AND name = ?
                """,
                (target_project_id, source_project_id, name),
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
            project_id=int(
                row["project_id"],
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
