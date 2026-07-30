"""
Database manager.
"""

from pathlib import Path

from core.constants import DATABASE_FILE

from .connection import DatabaseConnection
from .executor import MigrationExecutor
from .registry import MigrationRegistry


class DatabaseManager:

    def __init__(
        self,
        context,
        database: Path = DATABASE_FILE,
    ):

        self._context = context

        self._connection = DatabaseConnection(database)

        self._registry = MigrationRegistry()

        self._executor = MigrationExecutor(
            self._connection,
            self._registry,
            self._context,
        )

    def initialize(self):

        DATABASE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._registry.discover()

        self._executor.execute()

    def close(self):

        self._connection.close()

    def migrate(self):

        # self._connection.connect()
        self.initialize()

        # self._registry.discover()

        # self._executor.execute()

    # --------------------------------------
    # Helper
    # --------------------------------------
    @property
    def connection(self):

        return self._connection
