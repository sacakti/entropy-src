"""
Make command.
"""

from __future__ import annotations

from argparse import ArgumentParser
from argparse import Namespace

from core.commands.base import BaseCommand
from core.commands.base import CommandMetadata


class MakeCommand(BaseCommand):
    """
    Generate framework artifacts.
    """

    metadata = CommandMetadata(
        name="make",
        description="Generate framework artifacts.",
    )

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        parser.add_argument(
            "type",
            help="Artifact type.",
        )

        parser.add_argument(
            "name",
            help="Artifact name.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        assert self.context.generator_manager is not None

        self.context.generator_manager.generate(
            artifact=args.type,
            name=args.name,
        )
