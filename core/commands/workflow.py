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
from lib.workflow.follower import WorkflowFollower

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

        self._context = context

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

        jobs = subparsers.add_parser(
            "jobs",
            help="List workflow jobs.",
        )

        follow = subparsers.add_parser(
            "follow",
            help="Follow a workflow.",
        )

        follow.add_argument(
            "--pid",
            type=int,
            required=True,
            help="Workflow process ID.",
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
            "jobs": self._jobs,
            "follow": self._follow,
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

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def _jobs(
        self,
        args: Namespace,
    ) -> None:

        jobs = self._workflows.jobs()

        self._context.ui.table(
            title="Workflow Jobs",
            columns=[
                "ID",
                "Workflow",
                "State",
                "PID",
                "Started",
            ],
            rows=[
                [
                    job.id,
                    job.workflow,
                    job.state.value,
                    job.pid or "",
                    job.started_at or "",
                ]
                for job in jobs
            ],
        )

    # ------------------------------------------------------------------
    # Follow
    # ------------------------------------------------------------------

    def _follow(
        self,
        args: Namespace,
    ) -> None:

        self._workflows.follow(
            args.pid,
        )
