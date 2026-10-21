"""
Workflow drafts: definitions saved with errors ("Save with errors").

The workflow registry only holds valid workflows. A draft keeps the text
as written (even if it does not parse) so it can be finished later; it
cannot run. Saving the workflow successfully removes its draft.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
        }
        if full:
            item["definition"] = row["definition"]
        return item

    def list(self) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall("SELECT * FROM workflow_drafts ORDER BY updated_at DESC")
        return [self._row(row) for row in rows]

    def get(self, draft_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM workflow_drafts WHERE id = ?", (draft_id,))
        return self._row(row, full=True) if row else None

    def for_workflow(self, workflow: str) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT * FROM workflow_drafts WHERE workflow = ? ORDER BY updated_at DESC LIMIT 1",
            (workflow,),
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
    ) -> Dict[str, Any]:
        import json

        now = _now()
        # One draft per existing workflow: editing it again replaces it.
        if draft_id is None and workflow:
            existing = self.for_workflow(workflow)
            draft_id = existing["id"] if existing else None
        with self.connection.transaction():
            if draft_id is not None and self.get(draft_id) is not None:
                self.connection.execute(
                    "UPDATE workflow_drafts SET workflow = ?, title = ?, format = ?,"
                    " definition = ?, errors = ?, updated_by = ?, updated_at = ? WHERE id = ?",
                    (workflow, title, format, definition, json.dumps(errors), user, now, draft_id),
                )
            else:
                cursor = self.connection.execute(
                    "INSERT INTO workflow_drafts (workflow, title, format, definition, errors,"
                    " created_by, updated_by, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (workflow, title, format, definition, json.dumps(errors), user, user, now, now),
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

    def delete_for_workflow(self, workflow: str) -> None:
        with self.connection.transaction():
            self.connection.execute("DELETE FROM workflow_drafts WHERE workflow = ?", (workflow,))
