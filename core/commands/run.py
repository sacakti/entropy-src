"""
Run command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import BaseCommand, CommandMetadata


class RunCommand(BaseCommand):
    """
    Execute a workflow.
    """

    metadata = CommandMetadata(
        name="run",
        description="Run a plugin as a standalone application",
    )

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        parser.add_argument(
            "plugin",
            nargs="?",
            default="default",
            help="Plugin name",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        pass
