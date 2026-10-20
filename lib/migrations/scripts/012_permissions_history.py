"""
Read/write/delete/execute/all permissions for workflows and plugins, a
delete permission type for every module, and the version history of
workflows and plugins.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.migrations.base import BaseMigration


class PermissionsHistoryMigration(BaseMigration):
    """
    Reconcile the permission catalogue (renames move existing grants) and
    create the definition history table.
    """

    VERSION = 12

    DESCRIPTION = "Workflow and plugin permissions by type; version history."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """Apply the new permission catalogue and create the history table."""

        from lib.authorization.initializer import AuthorizationInitializer
        from lib.history import ensure_history_schema

        AuthorizationInitializer(connection).reconcile()
        ensure_history_schema(connection)
