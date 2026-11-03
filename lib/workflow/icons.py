"""
The icon chosen for each workflow, shared by everyone in its project.

Keyed by workflow_key, as names are only unique within a project. Replacing a workflow's
definition keeps its icon. The browser holds the icon collection (see lib/plugins/icons.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from lib.database.connection import DatabaseConnection
from lib.plugins.icons import validate_icon


def ensure_workflow_icons_schema(connection: DatabaseConnection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS workflow_icons ("
        "workflow TEXT PRIMARY KEY, icon TEXT NOT NULL,"
        "updated_by TEXT NOT NULL, updated_at TEXT NOT NULL"
        ")"
    )


class WorkflowIconStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_workflow_icons_schema(connection)
        self.connection = connection

    def all(self) -> Dict[str, str]:
        rows = self.connection.fetchall("SELECT workflow, icon FROM workflow_icons")
        return {row["workflow"]: row["icon"] for row in rows}

    def set(self, workflow: str, icon: Optional[str], updated_by: str) -> None:
        """Choose an icon; None goes back to the default."""

        if icon is None:
            self.forget(workflow)
            return
        validate_icon(icon)
        with self.connection.transaction():
            self.connection.execute(
                "INSERT OR REPLACE INTO workflow_icons"
                " (workflow, icon, updated_by, updated_at) VALUES (?, ?, ?, ?)",
                (workflow, icon, updated_by, datetime.now(timezone.utc).isoformat()),
            )

    def forget(self, workflow: str) -> None:
        with self.connection.transaction():
            self.connection.execute("DELETE FROM workflow_icons WHERE workflow = ?", (workflow,))

    def move(self, old: str, new: str) -> None:
        """The workflow moved to another project."""

        with self.connection.transaction():
            self.connection.execute(
                "UPDATE workflow_icons SET workflow = ? WHERE workflow = ?", (new, old)
            )

    def copy(self, source: str, target: str, updated_by: str) -> None:
        """A copy of the workflow looks like the original."""

        icon = self.all().get(source)
        if icon is not None:
            self.set(target, icon, updated_by)
