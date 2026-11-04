"""
Database manager.
"""

from __future__ import annotations

from lib.database import engine as database_engine
from lib.database.connection import DatabaseConnection
from lib.database.safety import DatabaseSafety


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
        # assert context.observability is not None

        self._context = context

        self._database = context.paths.database.file

        self._connection = database_engine.connection_for(
            context,
            self._database,
        )

        #
        # The guard, the lock and file backups protect the SQLite file;
        # another engine's server looks after its own data.
        #

        self.safety = (
            DatabaseSafety(self._database) if self.engine == database_engine.SQLITE else None
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """
        Open the application database.
        """

        self._context.executor.mkdir(
            self._database.parent,
            parents=True,
            exist_ok=True,
        )

        #
        # A missing database is put back (from its guard or a backup)
        # rather than silently replaced by an empty one.
        #

        if self.safety is not None:
            self.safety.ensure_present()

        self._connection.open()

    def close(self) -> None:
        """
        Close the active database connection.
        """

        self._connection.close()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def engine(self) -> str:
        """
        The engine in use: sqlite, or the one recorded by a switch.
        """

        return database_engine.engine_name(self._database)

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
