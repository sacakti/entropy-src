"""
Help command.
"""

from __future__ import annotations

from core.commands.base import BaseCommand
from core.commands.base import CommandMetadata


class HelpCommand(BaseCommand):
    """
    Display available commands.
    """

    metadata = CommandMetadata(
        name="help",
        description="Display available commands.",
        authentication_required=False,
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.command_manager is not None
        assert context.ui is not None

        self._commands = context.command_manager
        self._ui = context.ui

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser,
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
        args,
    ) -> None:
        """
        Display available commands.
        """

        self._ui.rule(
            "Available Commands",
        )

        for command in self._commands.list():

            if command.metadata.hidden:
                continue

            self._ui.print(
                "{0:<18}{1}".format(
                    command.metadata.name,
                    command.metadata.description,
                )
            )
