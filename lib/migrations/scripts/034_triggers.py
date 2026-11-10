"""Add webhook and queue triggers."""

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class TriggersMigration(BaseMigration):
    VERSION = 34
    DESCRIPTION = "Add webhook and queue triggers."

    def upgrade(self, connection: DatabaseConnection) -> None:
        from lib.triggers.store import ensure_trigger_schema

        ensure_trigger_schema(connection)
        from lib.authorization.initializer import AuthorizationInitializer

        # The triggers.* permissions, and the built-in roles that hold them.
        AuthorizationInitializer(connection).reconcile()
