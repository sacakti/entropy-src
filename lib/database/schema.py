"""
Database installer.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.objects import (
    ExtensionsTable,
    Indexes,
    PluginRegistryTable,
    SchemaMigrationsTable,
    SettingsTable,
    UsersTable,
    WorkflowEventsTable,
    WorkflowJobsTable,
    WorkflowsTable,
)


class SchemaInstaller:
    """
    Installs the canonical database schema.
    """

    def __init__(self) -> None:

        self._objects = (
            SchemaMigrationsTable(),
            SettingsTable(),
            PluginRegistryTable(),
            UsersTable(),
            WorkflowsTable(),
            ExtensionsTable(),
            WorkflowEventsTable(),
            WorkflowJobsTable(),
            Indexes(),
        )

    def install(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """
        Install the canonical database schema.
        """

        with connection.transaction():

            for database_object in self._objects:

                database_object.create(
                    connection,
                )
