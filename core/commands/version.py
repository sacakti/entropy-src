"""
Help command.
"""

from __future__ import annotations

from core.commands.base import BaseCommand, CommandMetadata
from version import APP_NAME, VERSION


class HelpCommand(BaseCommand):

    metadata = CommandMetadata(
        name="version",
        description="Display entropy version.",
        authentication_required=False,
    )

    def configure(self, parser):
        pass

    def execute(self, args):

        self.context.output.print(f"{APP_NAME} Version {VERSION}")