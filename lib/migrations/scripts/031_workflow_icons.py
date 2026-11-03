"""Add the icon chosen for each workflow."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class WorkflowIconsMigration(BaseMigration):
    VERSION = 31
    DESCRIPTION = "Add workflow icons."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.workflow.icons import ensure_workflow_icons_schema

        ensure_workflow_icons_schema(connection)
