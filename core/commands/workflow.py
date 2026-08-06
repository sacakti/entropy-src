"""
Workflow command.
"""

from __future__ import annotations

from argparse import (
    ArgumentParser,
    Namespace,
)
from pathlib import Path

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)


class WorkflowCommand(
    BaseCommand,
):
    """
    Workflow management command.
    """

    metadata = CommandMetadata(
        name="workflow",
        description="Execute workflows.",
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.workflow_manager is not None
        assert context.observability is not None

        self._workflows = context.workflow_manager

        self._events = context.observability.emitter(
            "workflow",
        )

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        subparsers = parser.add_subparsers(
            dest="action",
            required=True,
        )

        #
        # run
        #

        run = subparsers.add_parser(
            "run",
            help="Run a workflow.",
        )

        run.add_argument(
            "workflow",
            help="Workflow file.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:

        {
            "run": self._run,
        }[
            args.action
        ](
            args,
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _run(
        self,
        args: Namespace,
    ) -> None:
        """
        Execute a workflow.
        """

        workflow = Path(
            args.workflow,
        )

        self._events.log.info(
            f"Executing workflow '{workflow}'.",
        )

        self._workflows.run(
            workflow,
        )

        self._events.log.info(
            f"Workflow '{workflow}' completed.",
        )
