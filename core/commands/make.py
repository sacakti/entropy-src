"""
Make command.
"""

from __future__ import annotations

from core.commands.base import BaseCommand, CommandMetadata


class MakeCommand(BaseCommand):

    metadata = CommandMetadata(
        name="make",
        description="Generate framework artifacts.",
        authentication_required=True,
    )

    def configure(self, parser):

        parser.add_argument(
            "type",
            help="Artifact type.",
        )

        parser.add_argument(
            "--name",
            required=True,
            help="Artifact name.",
        )

    def execute(self, args):

        self.context.generator_manager.generate(
            args.type,
            args,
        )