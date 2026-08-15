"""
Document formatting command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from lib.formatter import FormatterManager


class FormatCommand(
    BaseCommand,
):
    """
    Format JSON, YAML and SQL documents.
    """

    metadata = CommandMetadata(
        name="format",
        description="Format a JSON, YAML or SQL file.",
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.formatter is not None
        assert context.ui is not None

        self._formatter: FormatterManager = context.formatter

        self._ui = context.ui

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        parser.add_argument(
            "file",
            type=Path,
            help="Source file to format.",
        )

        parser.add_argument(
            "-t",
            "--type",
            dest="format",
            choices=[
                "json",
                "yaml",
                "yml",
                "sql",
            ],
            help=(
                "Explicit document format. "
                "Must match the source file extension."
            ),
        )

        output = parser.add_mutually_exclusive_group()

        output.add_argument(
            "-d",
            "--destination",
            type=Path,
            help="Destination file. If omitted, the source is replaced in-place.",
        )

        output.add_argument(
            "--show",
            action="store_true",
            help="Show formatted content instead of writing it.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        self._format(
            args,
        )

    # ------------------------------------------------------------------
    # Format
    # ------------------------------------------------------------------

    def _format(
        self,
        args: Namespace,
    ) -> None:

        if args.show:

            content = self._formatter.format_file_content(
                source=args.file,
                format=args.format,
            )

            print(content, end="")

            return

        destination = self._formatter.format_file(
            source=args.file,
            format=args.format,
            destination=args.destination,
        )

        if args.destination is None:

            self._ui.success(
                f"Formatted '{destination}'.",
            )

            return

        self._ui.success(
            f"Formatted '{args.file}' -> '{destination}'.",
        )
