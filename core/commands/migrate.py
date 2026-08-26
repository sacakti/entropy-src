from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)

if TYPE_CHECKING:
    from core.context import EntropyContext


class MigrateCommand(BaseCommand):
    """
    Apply pending database migrations.
    """

    metadata = CommandMetadata(
        name="migrate",
        description="Apply pending database migrations.",
        aliases=("mig",),
    )

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.migration_manager is not None
        assert context.authorization is not None
        assert context.session_manager is not None

        self._migration = context.migration_manager

        self._authorization = context.authorization

        self._session = context.session_manager

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        pass

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        session = self._session.require()

        self._authorization.require(
            session,
            "migrate.database",
        )

        self._migration.migrate()
