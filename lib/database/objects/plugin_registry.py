"""
Plugin registry table.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class PluginRegistryTable(DatabaseObject):
    """
    Stores plugins registered with Entropy.
    """

    NAME = "plugin_registry"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS plugin_registry
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,

                name            TEXT NOT NULL UNIQUE,

                namespace       TEXT NOT NULL,

                version         TEXT NOT NULL,

                enabled         INTEGER NOT NULL DEFAULT 1,

                installed_at    TEXT NOT NULL
            )
            """
        )
