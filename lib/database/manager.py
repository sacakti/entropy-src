"""
Database manager.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.installer import DatabaseInstaller


class DatabaseManager:
    """
    Database subsystem.

    Responsibilities
    ----------------
    - Manage the database connection.
    - Install the canonical database schema.
    - Expose the active database connection.

    Schema evolution (migrations) is handled by the
    migration subsystem.
    """

    def __init__(
        self,
        context,
    ) -> None:

        assert context.paths is not None
        assert context.executor is not None
        assert context.observability is not None

        self._context = context

        self._database = context.paths.database.file

        self._connection = DatabaseConnection(
            self._database,
        )

        self._installer = DatabaseInstaller()

        self._log = context.diagnostics.logger(
            "system",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Prepare the database directory.
        """

        self._context.executor.mkdir(
            self._database.parent,
            parents=True,
            exist_ok=True,
        )

        self._connection.open()

    def prepare(self) -> None:
        """
        Prepare the database for use.
        """

        self.initialize()

        if not self._connection.table_exists(
            "schema_migrations",
        ):

            self.install()

    def install(self) -> None:
        """
        Install the canonical database schema.
        """

        self._log.info(
            "Installing database schema.",
        )

        self._installer.install(
            self._connection,
        )

        self._log.success(
            "Database schema installed.",
        )

    def close(self) -> None:
        """
        Close the active database connection.
        """

        self._connection.close()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connection(self) -> DatabaseConnection:
        """
        Active database connection.
        """

        return self._connection

    @property
    def database(self):
        """
        Database file.
        """

        return self._database
