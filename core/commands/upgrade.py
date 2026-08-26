"""
Upgrade command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)

if TYPE_CHECKING:
    from core.context import EntropyContext


class UpgradeCommand(
    BaseCommand,
):
    """
    Upgrade the Entropy application.
    """

    metadata = CommandMetadata(
        name="upgrade",
        description="Upgrade Entropy.",
        aliases=("up",),
    )

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.ui is not None
        assert context.authorization is not None
        assert context.session_manager is not None

        self._context = context

        self._ui = context.ui

        self._authorization = context.authorization

        self._session = context.session_manager

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        parser.add_argument(
            "--source",
            required=True,
            type=Path,
            help="Entropy .epkg upgrade package.",
        )

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
            "upgrade.entropy",
        )

        #
        # Import lazily so the upgrade subsystem isn't loaded
        # unless the command is actually used.
        #

        from lib.upgrade.manager import UpgradeManager

        self._ui.info(
            f"Upgrade package: {args.source}",
        )

        self._ui.info(
            "Validating upgrade package...",
        )

        UpgradeManager(
            self._context,
        ).upgrade(
            args.source,
        )

        self._ui.success(
            "Entropy upgraded successfully.",
        )
