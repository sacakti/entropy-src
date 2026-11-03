"""Add the icon chosen for each plugin."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class PluginIconsMigration(BaseMigration):
    VERSION = 29
    DESCRIPTION = "Add plugin icons."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.plugins.icons import ensure_plugin_icons_schema

        ensure_plugin_icons_schema(connection)
