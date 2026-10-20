"""
Earlier versions of workflows and plugins.

Before a workflow or plugin is changed, the version being replaced is kept
here, so users can compare it with the current one and restore it. Only
the last KEEP versions of each workflow or plugin are kept.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection

KEEP = 5
KINDS = ("workflow", "plugin")


def ensure_history_schema(connection: DatabaseConnection) -> None:
    """Create the history table once per connection."""

    if getattr(connection, "_entropy_history_ready", False):
        return

    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS definition_history
            (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                kind        TEXT NOT NULL CHECK (kind IN ('workflow', 'plugin')),
                name        TEXT NOT NULL,
                version     TEXT NOT NULL DEFAULT '',
                content     TEXT NOT NULL,
                reason      TEXT NOT NULL DEFAULT 'edit',
                created_by  TEXT,
                created_at  TEXT NOT NULL
            )
            """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_definition_history_item"
            " ON definition_history (kind, name, id)"
        )

    connection._entropy_history_ready = True


class DefinitionHistory:
    """The kept versions of one kind of definition (workflows or plugins)."""

    def __init__(self, connection: DatabaseConnection, kind: str) -> None:
        if kind not in KINDS:
            raise ValueError(f"Unknown history kind '{kind}'.")
        ensure_history_schema(connection)
        self.connection = connection
        self.kind = kind

    def record(
        self,
        name: str,
        version: str,
        content: Any,
        *,
        user: Optional[str] = None,
        reason: str = "edit",
    ) -> int:
        """Keep `content` (the version being replaced); drop all but the last KEEP."""

        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                INSERT INTO definition_history
                (kind, name, version, content, reason, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.kind,
                    name,
                    version or "",
                    json.dumps(content),
                    reason,
                    user,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self.connection.execute(
                """
                DELETE FROM definition_history
                WHERE kind = ? AND name = ? AND id NOT IN (
                    SELECT id FROM definition_history
                    WHERE kind = ? AND name = ?
                    ORDER BY id DESC LIMIT ?
                )
                """,
                (self.kind, name, self.kind, name, KEEP),
            )
        return int(cursor.lastrowid)

    def list(self, name: str) -> List[Dict[str, Any]]:
        """Kept versions, newest first, without their content."""

        rows = self.connection.fetchall(
            """
            SELECT id, version, reason, created_by, created_at
            FROM definition_history
            WHERE kind = ? AND name = ?
            ORDER BY id DESC
            """,
            (self.kind, name),
        )
        return [dict(row) for row in rows]

    def get(self, name: str, entry_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            """
            SELECT id, version, reason, created_by, created_at, content
            FROM definition_history
            WHERE kind = ? AND name = ? AND id = ?
            """,
            (self.kind, name, entry_id),
        )
        if row is None:
            return None
        entry = dict(row)
        entry["content"] = json.loads(entry["content"])
        return entry

    def forget(self, name: str) -> None:
        """Drop the history of a deleted workflow or plugin."""

        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM definition_history WHERE kind = ? AND name = ?",
                (self.kind, name),
            )
