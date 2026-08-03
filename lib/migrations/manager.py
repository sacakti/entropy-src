"""
Migration manager.
"""

from __future__ import annotations

from core.constants import DATABASE_MIGRATION_PACKAGE
from lib.database.connection import DatabaseConnection

from .executor import MigrationExecutor
from .history import MigrationHistory
from .registry import MigrationRegistry


class MigrationManager:
    """
    Database migration subsystem.
    """

    def __init__(self, context, package: str = DATABASE_MIGRATION_PACKAGE) -> None:

        assert context.database_manager is not None
        self._connection: DatabaseConnection = context.database_manager.connection

        from core.observability import NullEmitter

        if context.observability is not None:

            self._events = context.observability.emitter(
                "entropy",
            )

        else:

            self._events = NullEmitter()


        self._registry = MigrationRegistry(package)

        self._history = MigrationHistory(
            self._connection,
        )

        self._executor = MigrationExecutor(
            connection=self._connection,
            registry=self._registry,
            history=self._history,
            emitter=self._events,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """
        Discover available migrations.
        """

        self._registry.discover()

    def migrate(self) -> None:
        """
        Execute pending migrations.
        """

        self.discover()

        self._executor.execute()

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def register(
        self,
        migration,
    ) -> None:
        """
        Register a migration.
        """

        self._registry.register(
            migration,
        )

    def list(self):
        """
        Return registered migrations.
        """

        return self._registry.list()

    def get(
        self,
        version: int,
    ):
        """
        Return a migration.
        """

        return self._registry.get(
            version,
        )

    def clear(self) -> None:
        """
        Remove all registered migrations.
        """

        self._registry.clear()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    @property
    def history(self) -> MigrationHistory:
        """
        Migration history.
        """

        return self._history
