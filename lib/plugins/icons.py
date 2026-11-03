"""
The icon chosen for each plugin, shared by everyone.

Kept apart from plugin_registry and keyed by name, so a choice survives reinstalling or
upgrading the plugin, and drafts can have one too. The browser holds the icon collection:
here an icon is only a well-formed id, and one it does not know shows the default.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, Optional

from lib.database.connection import DatabaseConnection

_ICON = re.compile(r"^[a-z][a-z0-9-]{0,59}$")


class PluginIconError(ValueError):
    """An icon id that is not well formed."""


def ensure_plugin_icons_schema(connection: DatabaseConnection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS plugin_icons ("
        "qualified_name TEXT PRIMARY KEY, icon TEXT NOT NULL,"
        "updated_by TEXT NOT NULL, updated_at TEXT NOT NULL"
        ")"
    )


def validate_icon(icon: str) -> None:
    """Raise PluginIconError unless this is a well-formed icon id."""

    if not _ICON.match(icon):
        raise PluginIconError(f"'{icon}' is not a valid icon.")


class PluginIconStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_plugin_icons_schema(connection)
        self.connection = connection

    def all(self) -> Dict[str, str]:
        rows = self.connection.fetchall("SELECT qualified_name, icon FROM plugin_icons")
        return {row["qualified_name"]: row["icon"] for row in rows}

    def set(self, qualified_name: str, icon: Optional[str], updated_by: str) -> None:
        """Choose an icon; None goes back to the default."""

        if icon is None:
            self.forget(qualified_name)
            return
        validate_icon(icon)
        with self.connection.transaction():
            self.connection.execute(
                "INSERT OR REPLACE INTO plugin_icons"
                " (qualified_name, icon, updated_by, updated_at) VALUES (?, ?, ?, ?)",
                (qualified_name, icon, updated_by, datetime.now(timezone.utc).isoformat()),
            )

    def forget(self, qualified_name: str) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM plugin_icons WHERE qualified_name = ?", (qualified_name,)
            )
