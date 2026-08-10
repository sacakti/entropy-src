"""
Database manager.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection


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

        self._connection = DatabaseConnection(
            self._database,
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
