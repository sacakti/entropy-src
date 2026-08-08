"""
Make command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import BaseCommand, CommandMetadata


class MakeCommand(BaseCommand):
    """
    Generate framework artifacts.
    """

    metadata = CommandMetadata(
        name="generate",
        description="Generate framework artifacts.",
    )

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        subparsers = parser.add_subparsers(
            dest="generator",
            required=True,
        )

        plugin = subparsers.add_parser(
            "plugin",
            help="Generate a plugin.",
        )

        plugin.add_argument(
            "name",
            help="Plugin name.",
        )

        plugin.add_argument(
            "--namespace",
            default="custom",
            help="Plugin namespace.",
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
            name=args.generator,
            args=args,
        )
