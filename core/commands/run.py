"""
Run command.
"""

from __future__ import annotations

from argparse import ArgumentParser
from argparse import Namespace
from pathlib import Path

from core.commands.base import BaseCommand
from core.commands.base import CommandMetadata


class RunCommand(BaseCommand):
    """
    Execute a workflow.
    """

    metadata = CommandMetadata(
        name="run",
        description="Execute a workflow.",
    )

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        parser.add_argument(
            "workflow",
            nargs="?",
            default="default",
            help="Workflow name or workflow definition.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        assert self.context.workflow_manager is not None

        self.context.workflow_manager.load(
            Path(args.workflow),
        )

        self.context.workflow_manager.execute()
