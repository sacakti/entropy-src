"""
Workflow drafts: definitions saved with errors ("Save with errors").

The workflow registry only holds valid workflows. A draft keeps the text
as written (even if it does not parse) so it can be finished later; it
cannot run. Saving the workflow successfully removes its draft.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from lib.database.connection import DatabaseConnection


def ensure_drafts_schema(connection: DatabaseConnection) -> None:
    if getattr(connection, "_entropy_workflow_drafts_ready", False):
        return
    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS workflow_drafts
            (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow    TEXT,
                title       TEXT NOT NULL,
                format      TEXT NOT NULL CHECK (format IN ('json', 'yaml')),
                definition  TEXT NOT NULL,
                errors      TEXT NOT NULL DEFAULT '[]',
                project_id  INTEGER,
                created_by  TEXT,
                updated_by  TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_drafts_workflow ON workflow_drafts (workflow)"
        )
    connection._entropy_workflow_drafts_ready = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowDrafts:
    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_drafts_schema(connection)
        from lib.authorization.projects import add_project_columns

        # Databases with drafts from before projects.
        add_project_columns(connection)
        self.connection = connection

    @staticmethod
    def _row(row: Any, full: bool = False) -> Dict[str, Any]:
        import json

        item = {
            "id": row["id"],
            "workflow": row["workflow"],
            "title": row["title"],
            "format": row["format"],
            "errors": json.loads(row["errors"] or "[]"),
            "created_by": row["created_by"],
            "updated_by": row["updated_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "project_id": row["project_id"] if "project_id" in row.keys() else None,  # noqa: SIM118
        }
        if full:
            item["definition"] = row["definition"]
        return item

    def list(self, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Drafts, or only one project's (drafts from before projects belong to Default)."""

        if project_id is None:
            rows = self.connection.fetchall(
                "SELECT * FROM workflow_drafts ORDER BY updated_at DESC"
            )
        else:
            from lib.authorization.projects import default_project_id

            rows = self.connection.fetchall(
                "SELECT * FROM workflow_drafts WHERE IFNULL(project_id, ?) = ?"
                " ORDER BY updated_at DESC",
                (default_project_id(self.connection), project_id),
            )
        return [self._row(row) for row in rows]

    def get(self, draft_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM workflow_drafts WHERE id = ?", (draft_id,))
        return self._row(row, full=True) if row else None

    def _project_clause(self, project_id: Optional[int]) -> Tuple[str, Tuple[Any, ...]]:
        """Drafts of one project (drafts from before projects are the Default project's)."""

        from lib.authorization.projects import default_project_id

        default_id = default_project_id(self.connection)
        wanted = default_id if project_id is None else project_id
        return "IFNULL(project_id, ?) = ?", (default_id, wanted)

    def for_workflow(
        self, workflow: str, project_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """The draft of a project's workflow (names are unique per project)."""

        clause, values = self._project_clause(project_id)
        row = self.connection.fetchone(
            f"SELECT * FROM workflow_drafts WHERE workflow = ? AND {clause}"
            " ORDER BY updated_at DESC LIMIT 1",
            (workflow, *values),
        )
        return self._row(row) if row else None

    def save(
        self,
        *,
        draft_id: Optional[int],
        workflow: Optional[str],
        title: str,
        format: str,
        definition: str,
        errors: List[str],
        user: str,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        import json

        now = _now()
        # One draft per existing workflow: editing it again replaces it.
        if draft_id is None and workflow:
            existing = self.for_workflow(workflow, project_id)
            draft_id = existing["id"] if existing else None
        with self.connection.transaction():
            if draft_id is not None and self.get(draft_id) is not None:
                self.connection.execute(
                    "UPDATE workflow_drafts SET workflow = ?, title = ?, format = ?,"
                    " definition = ?, errors = ?, updated_by = ?, updated_at = ?,"
                    " project_id = ? WHERE id = ?",
                    (
                        workflow,
                        title,
                        format,
                        definition,
                        json.dumps(errors),
                        user,
                        now,
                        project_id,
                        draft_id,
                    ),
                )
            else:
                cursor = self.connection.execute(
                    "INSERT INTO workflow_drafts (workflow, title, format, definition, errors,"
                    " created_by, updated_by, created_at, updated_at, project_id)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        workflow,
                        title,
                        format,
                        definition,
                        json.dumps(errors),
                        user,
                        user,
                        now,
                        now,
                        project_id,
                    ),
                )
                draft_id = int(cursor.lastrowid)
        saved = self.get(draft_id)
        assert saved is not None
        return saved

    def delete(self, draft_id: int) -> bool:
        with self.connection.transaction():
            cursor = self.connection.execute(
                "DELETE FROM workflow_drafts WHERE id = ?", (draft_id,)
            )
        return cursor.rowcount > 0

    def delete_for_workflow(self, workflow: str, project_id: Optional[int] = None) -> None:
        clause, values = self._project_clause(project_id)
        with self.connection.transaction():
            self.connection.execute(
                f"DELETE FROM workflow_drafts WHERE workflow = ? AND {clause}",
                (workflow, *values),
            )
