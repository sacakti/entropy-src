"""
Make command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)

if TYPE_CHECKING:
    from core.context import EntropyContext


class MakeCommand(BaseCommand):
    """
    Generate framework artifacts.
    """

    metadata = CommandMetadata(
        name="generate",
        description="Generate framework artifacts.",
        aliases=("gen", "create"),
    )

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.generator_manager is not None
        assert context.authorization is not None
        assert context.session_manager is not None

        self._generator = context.generator_manager

        self._authorization = context.authorization

        self._session = context.session_manager

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
            "-n",
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

        session = self._session.require()

        self._authorization.require(
            session,
            "generate.plugin",
        )

        self._generator.generate(
            name=args.generator,
            args=args,
        )
