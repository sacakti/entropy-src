"""
Version command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from core.version import (
    APP_NAME,
    VERSION,
)


class VersionCommand(BaseCommand):
    """
    Display application version.
    """

    metadata = CommandMetadata(
        name="version",
        description="Display the application version.",
        authentication_required=False,
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.ui is not None

        self._ui = context.ui

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:
        """
        Configure command-line arguments.
        """

        pass

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:
        """
        Display the application version.
        """

        self._ui.print(f"{APP_NAME} Version {VERSION}")
