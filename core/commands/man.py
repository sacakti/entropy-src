"""
Entropy manual command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from lib.documentation.manager import DocumentationManager


class ManCommand(
    BaseCommand,
):
    """
    Display Entropy documentation.
    """

    metadata = CommandMetadata(
        name="man",
        description="Display Entropy documentation.",
        authentication_required=False,
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.bootstrap is not None
        assert context.paths is not None
        assert context.ui is not None

        self._documentation = DocumentationManager(
            documentation_path=(context.bootstrap.resources.documentation),
            generated_path=(context.paths.workspace.generated),
        )

        self._ui = context.ui

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        parser.add_argument(
            "--html",
            action="store_true",
            help="Generate the HTML support documentation.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        if args.html:

            path, generated = self._documentation.generate_html()

            if generated:

                self._ui.success(
                    f"Generated support documentation: {path}",
                )

            else:

                self._ui.info(
                    f"Support documentation is already up to date: " f"{path}",
                )

            return

        self._ui.markdown(
            self._documentation.render(),
            pager=True,
        )
