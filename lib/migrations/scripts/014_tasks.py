"""Add project task management."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class TasksMigration(BaseMigration):
    VERSION = 14
    DESCRIPTION = "Add project task management."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.tasks.store import ensure_tasks_schema

        ensure_tasks_schema(connection)
        from lib.authorization.initializer import AuthorizationInitializer

        AuthorizationInitializer(connection).reconcile()
