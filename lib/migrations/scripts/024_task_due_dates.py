"""Add task due dates and status history (closed tasks are reopened with a reason)."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class TaskDueDatesMigration(BaseMigration):
    VERSION = 24
    DESCRIPTION = "Add task due dates and status history."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.tasks.store import ensure_tasks_schema

        ensure_tasks_schema(connection)
