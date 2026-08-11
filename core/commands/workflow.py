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
from lib.workflow.exceptions import WorkflowInvalidProvidedError, WorkflowTooManyFilesError


class WorkflowCommand(
    BaseCommand,
):
    """
    Workflow management command.
    """

    metadata = CommandMetadata(
        name="workflow",
        description="Execute workflows.",
        aliases=(
            "workflows",
            "wf",
        ),
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
        # add
        #

        add = subparsers.add_parser(
            "add",
            help="Register a workflow.",
        )

        add.add_argument(
            "file",
            type=Path,
            help="Workflow definition file (.json, .yaml, .yml).",
        )

        #
        # remove
        #

        remove = subparsers.add_parser(
            "remove",
            help="Remove a registered workflow.",
        )

        remove.add_argument(
            "name",
            help="Registered workflow name.",
        )

        #
        # list
        #

        subparsers.add_parser(
            "list",
            help="List registered workflows.",
        )

        #
        # show
        #

        show = subparsers.add_parser(
            "show",
            help="Show a registered workflow.",
        )

        show.add_argument(
            "name",
            help="Registered workflow name.",
        )

        output = show.add_mutually_exclusive_group()

        output.add_argument(
            "--json",
            action="store_true",
            help="Display the workflow as JSON.",
        )

        output.add_argument(
            "--yaml",
            action="store_true",
            help="Display the workflow as YAML.",
        )

        #
        # edit
        #

        edit = subparsers.add_parser(
            "edit",
            help="Edit a registered workflow.",
        )

        edit.add_argument(
            "name",
            help="Registered workflow name.",
        )

        #
        # replace
        #

        replace = subparsers.add_parser(
            "replace",
            help="Replace a registered workflow definition.",
        )

        replace.add_argument(
            "name",
            help="Registered workflow name.",
        )

        replace.add_argument(
            "-f",
            "--from-file",
            type=Path,
            required=True,
            help="Workflow definition file.",
        )

        #
        # run
        #

        run = subparsers.add_parser(
            "run",
            help="Run a registered workflow or workflow file.",
        )

        run.add_argument(
            "workflow",
            nargs="?",
            help="Registered workflow name.",
        )

        run.add_argument(
            "-f",
            "--from-file",
            type=Path,
            help="Run a workflow definition from a file.",
        )

        #
        # start
        #

        start = subparsers.add_parser(
            "start",
            help="Start a registered workflow or workflow file in the background.",
        )

        start.add_argument(
            "workflow",
            nargs="?",
            help="Registered workflow name.",
        )

        start.add_argument(
            "-f",
            "--from-file",
            type=Path,
            help="Start a workflow definition from a file.",
        )

        #
        # jobs
        #

        subparsers.add_parser(
            "jobs",
            help="List workflow jobs.",
        )

        #
        # follow
        #

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
            "add": self._add,
            "remove": self._remove,
            "list": self._list,
            "show": self._show,
            "edit": self._edit,
            "replace": self._replace,
            "run": self._run,
            "start": self._start,
            "jobs": self._jobs,
            "follow": self._follow,
            "stop": self._stop,
        }[args.action](
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
        Execute a registered workflow or workflow file.
        """

        workflow_name, workflow_file = self._workflow_source(
            args,
        )

        if workflow_file is not None:

            self._events.log.info(
                f"Executing workflow from '{workflow_file}'.",
            )

            self._workflows.run(
                file=workflow_file,
            )

            self._events.log.info(
                f"Workflow file '{workflow_file}' completed.",
            )

            return

        assert workflow_name is not None

        self._events.log.info(
            f"Executing workflow '{workflow_name}'.",
        )

        self._workflows.run(
            name=workflow_name,
        )

        self._events.log.info(
            f"Workflow '{workflow_name}' completed.",
        )

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def _start(
        self,
        args: Namespace,
    ) -> None:
        """
        Start a registered workflow or workflow file in the background.
        """

        workflow_name, workflow_file = self._workflow_source(
            args,
        )

        if workflow_file is not None:

            job = self._workflows.start(
                file=workflow_file,
            )

        else:

            assert workflow_name is not None

            job = self._workflows.start(
                name=workflow_name,
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

            if not job:

                self._context.ui.warning(
                    f"No active workflow found with id " f"'{args.pid}'.",
                )

                return

            self._context.ui.success(
                f"Stop requested for workflow " f"'{job.workflow}' (PID {job.pid}).",
            )

            return

        if args.name is not None:

            jobs = [
                job for job in self._workflows.jobs() if job.workflow == args.name and job.running
            ]

            if not jobs:

                self._context.ui.warning(
                    f"No active workflow found with name " f"'{args.name}'.",
                )

                return

            for job in jobs:

                self._workflows.stop(
                    job.pid,
                )

                self._context.ui.success(
                    f"Stop requested for workflow " f"'{job.workflow}' (PID {job.pid}).",
                )

            return

        if args.all:

            jobs = [job for job in self._workflows.jobs() if job.running]

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
                    f"Stop requested for workflow " f"'{job.workflow}' (PID {job.pid}).",
                )

    # Add a workflow
    def _add(
        self,
        args: Namespace,
    ) -> None:
        """
        Register a workflow definition.
        """

        workflow = self._workflows.add(
            args.file,
        )

        self._context.ui.success(
            f"Workflow '{workflow.name}' added successfully.",
        )

    def _remove(
        self,
        args: Namespace,
    ) -> None:
        """
        Remove a registered workflow.
        """

        self._workflows.remove(
            args.name,
        )

        self._context.ui.success(
            f"Workflow '{args.name}' removed successfully.",
        )

    def _list(
        self,
        args: Namespace,
    ) -> None:
        """
        List registered workflows.
        """

        workflows = self._workflows.list()

        if not workflows:

            self._context.ui.info(
                "No workflows registered.",
            )

            return

        self._context.ui.table(
            title="Registered Workflows",
            columns=[
                "Name",
                "Version",
                "Description",
                "Created",
                "Updated",
            ],
            rows=[
                [
                    workflow.name,
                    workflow.version,
                    workflow.description or "",
                    workflow.created_at.isoformat(),
                    workflow.updated_at.isoformat(),
                ]
                for workflow in workflows
            ],
        )

    def _show(
        self,
        args: Namespace,
    ) -> None:
        """
        Show a registered workflow.
        """

        workflow = self._workflows.get(
            args.name,
        )

        if args.json:

            self._context.ui.print(
                self._workflows.serialize(
                    workflow,
                    "json",
                ),
            )

            return

        if args.yaml:

            self._context.ui.print(
                self._workflows.serialize(
                    workflow,
                    "yaml",
                ),
            )

            return

        self._context.ui.rule(
            f"Workflow : {workflow.name}",
        )

        self._context.ui.table(
            title="Metadata",
            columns=[
                "Property",
                "Value",
            ],
            rows=[
                [
                    "Name",
                    workflow.name,
                ],
                [
                    "Version",
                    workflow.version,
                ],
                [
                    "Description",
                    workflow.description or "",
                ],
                [
                    "Steps",
                    workflow.step_count,
                ],
            ],
        )

        self._context.ui.info(
            "Variables:",
        )

        self._context.ui.print(
            workflow.variables,
        )

        self._context.ui.info(
            "Steps:",
        )

        self._context.ui.table(
            title="Workflow Steps",
            columns=[
                "Name",
                "Plugin",
                "Enabled",
                "Tags",
                "On Failure",
            ],
            rows=[
                [
                    step.name,
                    step.plugin,
                    "Yes" if step.enabled else "No",
                    ", ".join(step.tags),
                    step.on_failure,
                ]
                for step in workflow.steps
            ],
        )

    def _replace(
        self,
        args: Namespace,
    ) -> None:
        """
        Replace a registered workflow from a file.
        """

        workflow = self._workflows.replace(
            args.name,
            args.from_file,
        )

        self._context.ui.success(
            f"Workflow '{workflow.name}' replaced successfully.",
        )

    def _edit(
        self,
        args: Namespace,
    ) -> None:
        """
        Edit a registered workflow.
        """

        result = self._workflows.edit(
            args.name,
        )

        if result.changed:

            self._context.ui.success(
                f"Workflow '{result.workflow.name}' "
                "updated successfully.",
            )

        else:

            self._context.ui.info(
                f"Workflow '{result.workflow.name}' "
                "was not changed.",
            )

    def _workflow_source(
        self,
        args: Namespace,
    ) -> tuple[str | None, Path | None]:
        """
        Resolve the workflow source supplied by the user.
        """

        if args.workflow is not None and args.from_file is not None:

            raise WorkflowTooManyFilesError

        if args.workflow is None and args.from_file is None:

            raise WorkflowInvalidProvidedError

        return (
            args.workflow,
            args.from_file,
        )
