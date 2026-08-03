"""
Database installation.
"""

from __future__ import annotations

from core.context import EntropyContext
from lib.database.schema import SchemaInstaller


class DatabaseInstaller:
    """
    Installs the application database.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.database_manager is not None
        assert context.migration_manager is not None

        self._database = context.database_manager
        self._migrations = context.migration_manager
        self._schema = SchemaInstaller()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def install(self) -> None:
        """
        Install the application database.
        """

        self._database.open()

        self._schema.install(
            self._database.connection,
        )

        self._migrations.migrate()

        self._database.close()
