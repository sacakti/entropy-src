"""
Help command.
"""

from __future__ import annotations

from core.commands.base import BaseCommand, CommandMetadata


class HelpCommand(BaseCommand):

    metadata = CommandMetadata(
        name="help",
        description="Display available commands.",
    )

    def configure(self, parser):
        pass

    def execute(self, args):

        self.context.output.rule("Available Commands")

        for command in self.context.command_manager.list():

            if command.metadata.hidden:
                continue

            self.context.output.print(

                f"{command.metadata.name:<18}"

                f"{command.metadata.description}"
            )