"""
Deploy command.
"""

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)

from lib.workflow import Workflow


class DeployCommand(BaseCommand):

    metadata = CommandMetadata(
        name="deploy",
        description="Execute a workflow.",
    )

    def configure(self, parser):

        parser.add_argument(
            "--workflow",
            default="default",
            help="Workflow name.",
        )

    def execute(self, args):

        workflow = Workflow(self.context)

        workflow.load(args.workflow)

        workflow.execute()