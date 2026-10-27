"""Add task types, keys, external references, groups and attachments."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class TaskExtensionsMigration(BaseMigration):
    VERSION = 23
    DESCRIPTION = "Add task types, keys (ENTASK-01), external references, groups and attachments."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.tasks.store import ensure_tasks_schema

        ensure_tasks_schema(connection)
