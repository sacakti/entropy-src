"""
Migration executor.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.migrations.exceptions import MigrationExecutionError
from lib.migrations.history import MigrationHistory
from lib.migrations.registry import MigrationRegistry


class MigrationExecutor:
    """
    Executes pending database migrations.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
        registry: MigrationRegistry,
        history: MigrationHistory,
        emitter,
    ) -> None:

        self._connection = connection

        self._registry = registry

        self._history = history

        self._events = emitter

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self) -> None:
        """
        Execute all pending migrations.
        """

        applied = set(
            self._history.applied(),
        )

        pending = [
            migration for migration in self._registry.list() if migration.VERSION not in applied
        ]

        if not pending:

            self._info(
                "Database schema is up to date.",
            )

            return

        self._info(
            f"Applying {len(pending)} migration(s).",
        )

        for migration in pending:

            self._execute(
                migration,
            )

        self._info(
            "Database migration completed.",
        )

    # ------------------------------------------------------------------
    # Execute Migration
    # ------------------------------------------------------------------

    def _execute(
        self,
        migration,
    ) -> None:
        """
        Execute a single migration.
        """

        self._info(
            f"{migration.VERSION:03d} {migration.DESCRIPTION}",
        )

        try:

            migration.validate()

            with self._connection.transaction():

                migration.upgrade(
                    self._connection,
                )

                self._history.record(
                    migration.VERSION,
                    migration.DESCRIPTION,
                )

        except Exception as exc:
            import traceback

            traceback.print_exc()

            self._error(
                f"Migration {migration.VERSION:03d} failed.",
            )

            raise MigrationExecutionError(f"Migration {migration.VERSION:03d} failed.") from exc

        self._info(
            f"Applied {migration.VERSION:03d}",
        )

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _info(
        self,
        message: str,
    ) -> None:

        if self._events is not None:

            self._events.log.info(
                message,
            )

    def _error(
        self,
        message: str,
    ) -> None:

        if self._events is not None:

            self._events.log.error(
                message,
            )
