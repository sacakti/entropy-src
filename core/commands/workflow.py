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
        aliases=("workflows","wf",),
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

        #
        # start
        #

        start = subparsers.add_parser(
            "start",
            help="Start a workflow in the background.",
        )

        start.add_argument(
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

        #
        # stop
        #

        stop = subparsers.add_parser(
            "stop",
            help="Stop workflow processes.",
        )

        selectors = stop.add_mutually_exclusive_group(
            required=True,
        )

        selectors.add_argument(
            "--pid",
            type=int,
            help="Stop one workflow process by PID.",
        )

        selectors.add_argument(
            "--name",
            help="Stop all active workflow processes with this name.",
        )

        selectors.add_argument(
            "--all",
            action="store_true",
            help="Stop all active workflow processes.",
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
            "start": self._start,
            "jobs": self._jobs,
            "follow": self._follow,
            "stop": self._stop,
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
    # Start
    # ------------------------------------------------------------------

    def _start(
        self,
        args: Namespace,
    ) -> None:
        """
        Start a workflow in the background.
        """

        workflow = Path(
            args.workflow,
        )

        job = self._workflows.start(
            workflow,
        )

        self._context.ui.success(
            f"Workflow '{job.workflow}' started in background.",
        )

        self._context.ui.info(
            f"PID : {job.pid}",
        )

        self._context.ui.info(
            f"Follow : ent workflow follow --pid {job.pid}",
        )

        self._context.ui.info(
            f"Stop   : ent workflow stop --pid {job.pid}",
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

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def _stop(
        self,
        args: Namespace,
    ) -> None:
        """
        Stop workflow processes.
        """

        if args.pid is not None:

            job = self._workflows.stop(
                args.pid,
            )

            self._context.ui.success(
                f"Stop requested for workflow "
                f"'{job.workflow}' (PID {job.pid}).",
            )

            return

        if args.name is not None:

            jobs = [
                job
                for job in self._workflows.jobs()
                if job.workflow == args.name
                and job.running
            ]

            if not jobs:

                self._context.ui.warning(
                    f"No active workflow found with name "
                    f"'{args.name}'.",
                )

                return

            for job in jobs:

                self._workflows.stop(
                    job.pid,
                )

                self._context.ui.success(
                    f"Stop requested for workflow "
                    f"'{job.workflow}' (PID {job.pid}).",
                )

            return

        if args.all:

            jobs = [
                job
                for job in self._workflows.jobs()
                if job.running
            ]

            if not jobs:

                self._context.ui.info(
                    "No active workflows.",
                )

                return

            for job in jobs:

                self._workflows.stop(
                    job.pid,
                )

                self._context.ui.success(
                    f"Stop requested for workflow "
                    f"'{job.workflow}' (PID {job.pid}).",
                )
