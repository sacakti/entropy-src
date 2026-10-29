"""
Workflow command.
"""

from __future__ import annotations

from argparse import (
    ArgumentParser,
    Namespace,
)
from pathlib import Path
from typing import TYPE_CHECKING

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)
from core.commands.output_mode import (
    add_output_argument,
    emit,
    output_mode,
)
from core.commands.project_context import ProjectContext
from lib.authorization.exceptions import AuthorizationRequiredError
from lib.models.workflow import WorkflowExecutionOptions
from lib.remote_cli.contract import canonical_verb
from lib.remote_cli.output import when
from lib.runs.store import RunStore
from lib.workflow.assignments import WorkflowAssignments
from lib.workflow.exceptions import (
    WorkflowArgumentError,
    WorkflowInvalidProvidedError,
    WorkflowTooManyFilesError,
)

if TYPE_CHECKING:
    from core.context import EntropyContext


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
        context: EntropyContext,
    ) -> None:

        super().__init__(
            context,
        )

        self._context = context

        assert context.workflow_manager is not None
        assert context.observability is not None
        assert context.authorization is not None
        assert context.session_manager is not None

        self._workflows = context.workflow_manager

        self._assignments = WorkflowAssignments()

        self._events = context.observability.emitter(
            "workflow",
        )

        self._authorization = context.authorization

        self._session = context.session_manager

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
            "delete",
            aliases=[
                "remove",
                "rm",
            ],
            help="Delete a registered workflow.",
        )

        remove.add_argument(
            "name",
            help="Registered workflow name.",
        )

        remove.add_argument(
            "-y",
            "--yes",
            action="store_true",
            help="Accepted for the ent client's syntax; nothing is asked here.",
        )

        #
        # apply / validate (the ent client's file verbs)
        #

        for verb, text in (
            ("apply", "Create or update a workflow from a file."),
            ("validate", "Check a definition file without saving it."),
        ):

            item = subparsers.add_parser(
                verb,
                help=text,
            )

            item.add_argument(
                "-f",
                "--file",
                "--from-file",
                dest="file",
                type=Path,
                required=True,
                help="Workflow definition file (.json, .yaml, .yml).",
            )

        #
        # list
        #

        listing = subparsers.add_parser(
            "list",
            aliases=[
                "ls",
            ],
            help="List registered workflows.",
        )

        add_output_argument(
            listing,
        )

        #
        # show
        #

        show = subparsers.add_parser(
            "get",
            aliases=[
                "show",
                "describe",
            ],
            help="Show a registered workflow (-o yaml|json for its definition).",
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

        add_output_argument(
            output,
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

        run.add_argument(
            "--tags",
            help="Run only steps with the tags.",
        )

        run.add_argument(
            "--from-step",
            help="Start execution from this step.",
        )

        run.add_argument(
            "--to-step",
            help="Stop execution after this step.",
        )

        run.add_argument(
            "--skip-steps",
            nargs="+",
            default=[],
            metavar="STEP",
            help="Skip one or more workflow steps.",
        )

        run.add_argument(
            "--dry-run",
            action="store_true",
            help="Show selected steps without executing them.",
        )

        run.add_argument(
            "-a",
            "--arguments",
            "--var",
            dest="arguments",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help=(
                "Workflow variable override. "
                "May contain multiple assignments separated by ';'. "
                "May be specified multiple times."
            ),
        )

        run.add_argument(
            "--set",
            action="append",
            default=[],
            metavar="STEP.KEY=VALUE",
            help=(
                "Workflow step argument override. "
                "May contain multiple assignments separated by ';'. "
                "May be specified multiple times."
            ),
        )

        run.add_argument(
            "--separator",
            default=WorkflowAssignments.DEFAULT_SEPARATOR,
            help="Assignment separator. Default: ';'.",
        )

        run.add_argument(
            "--type",
            choices=(
                "auto",
                "string",
                "integer",
                "float",
                "boolean",
                "json",
                "list",
                "dict",
            ),
            default="auto",
            help=("Type of --set values. " "Default: auto."),
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

        start.add_argument(
            "--tags",
            help="Run only steps with tags.",
        )

        start.add_argument(
            "--from-step",
            help="Start execution from this step.",
        )

        start.add_argument(
            "--to-step",
            help="Stop execution after this step.",
        )

        start.add_argument(
            "--skip-steps",
            nargs="+",
            default=[],
            metavar="STEP",
            help="Skip one or more workflow steps.",
        )

        start.add_argument(
            "-a",
            "--arguments",
            "--var",
            dest="arguments",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help=(
                "Workflow variable override. "
                "May contain multiple assignments separated by ';'. "
                "May be specified multiple times."
            ),
        )

        start.add_argument(
            "--set",
            action="append",
            default=[],
            metavar="STEP.KEY=VALUE",
            help=(
                "Workflow step argument override. "
                "May contain multiple assignments separated by ';'. "
                "May be specified multiple times."
            ),
        )

        start.add_argument(
            "--separator",
            default=WorkflowAssignments.DEFAULT_SEPARATOR,
            help="Assignment separator. Default: ';'.",
        )

        start.add_argument(
            "--type",
            choices=(
                "auto",
                "string",
                "integer",
                "float",
                "boolean",
                "json",
                "list",
                "dict",
            ),
            default="auto",
            help=("Type of --set values. " "Default: auto."),
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
            "apply": self._apply,
            "validate": self._validate,
            "delete": self._remove,
            "list": self._list,
            "get": self._show,
            "edit": self._edit,
            "replace": self._replace,
            "run": self._run,
            "start": self._start,
            "jobs": self._jobs,
            "follow": self._follow,
            "stop": self._stop,
        }[canonical_verb("workflow", args.action)](
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

        session = self._session.require()
        project = ProjectContext(self._context).current(session)
        self._require("workflows.execute", project["id"])

        workflow_name, workflow_file = self._workflow_source(
            args,
        )

        options = self._execution_options(
            args,
        )

        if workflow_file is not None:

            source = f"workflow file '{workflow_file}'"

            self._events.log.info(
                (f"Previewing {source}." if options.dry_run else f"Executing {source}."),
            )

            job_id = self._workflows.run(
                file=workflow_file,
                options=options,
            )
            if job_id is not None:
                self._record_cli_run(job_id, workflow_file.stem, project["id"])

            self._events.log.info(
                (
                    f"{source.capitalize()} dry-run completed."
                    if options.dry_run
                    else f"{source.capitalize()} completed."
                ),
            )

            return

        assert workflow_name is not None

        source = f"workflow '{workflow_name}'"

        self._events.log.info(
            (f"Previewing {source}." if options.dry_run else f"Executing {source}."),
        )

        job_id = self._workflows.run(
            name=workflow_name,
            options=options,
            project_id=project["id"],
        )
        self._record_cli_run(job_id, workflow_name, project["id"])

        self._events.log.info(
            (
                f"{source.capitalize()} dry-run completed."
                if options.dry_run
                else f"{source.capitalize()} completed."
            ),
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

        session = self._session.require()
        project = ProjectContext(self._context).current(session)
        self._require("workflows.execute", project["id"])

        workflow_name, workflow_file = self._workflow_source(
            args,
        )

        options = self._start_execution_options(
            args,
        )

        #
        # start does not support dry-run.
        #

        options = WorkflowExecutionOptions(
            tags=options.tags,
            from_step=options.from_step,
            to_step=options.to_step,
            skip_steps=options.skip_steps,
            dry_run=False,
            variables=options.variables,
            step_overrides=options.step_overrides,
        )

        if workflow_file is not None:

            job = self._workflows.start(
                file=workflow_file,
                options=options,
            )
            target = workflow_file.stem

        else:

            assert workflow_name is not None

            job = self._workflows.start(
                name=workflow_name,
                options=options,
                project_id=project["id"],
            )
            target = workflow_name

        self._record_cli_run(job.require_id(), target, project["id"])

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

        self._require(
            "workflows.read",
        )

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

        self._require(
            "workflows.read",
        )

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

        self._require(
            "workflows.execute",
        )

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

        session = self._session.require()
        project = ProjectContext(self._context).current(session)
        self._require("workflows.write", project["id"])

        workflow = self._workflows.add(
            args.file,
            project_id=project["id"],
        )

        self._context.ui.success(
            f"Workflow '{workflow.name}' added successfully.",
        )

    def _apply(
        self,
        args: Namespace,
    ) -> None:
        """
        Create or update a workflow from a file (the ent client's apply).
        """

        session = self._session.require()
        project = ProjectContext(self._context).current(session)
        self._require("workflows.write", project["id"])

        name = self._workflows.load(args.file).name

        if self._workflows.exists(name, project_id=project["id"]):

            workflow = self._workflows.replace(
                name,
                args.file,
                project_id=project["id"],
            )

            self._context.ui.success(
                f"Workflow '{workflow.name}' updated (version {workflow.version}).",
            )

            return

        workflow = self._workflows.add(
            args.file,
            project_id=project["id"],
        )

        self._context.ui.success(
            f"Workflow '{workflow.name}' created (version {workflow.version}).",
        )

    def _validate(
        self,
        args: Namespace,
    ) -> None:
        """
        Check a workflow definition file without saving it.
        """

        self._project_id(
            "workflows.read",
        )

        workflow = self._workflows.load(
            args.file,
        )

        self._context.ui.success(
            f"Valid: {workflow.name} {workflow.version} with {workflow.step_count} "
            f"step{'' if workflow.step_count == 1 else 's'}.",
        )

    def _remove(
        self,
        args: Namespace,
    ) -> None:
        """
        Remove a registered workflow.
        """

        project_id = self._project_id(
            "workflows.delete",
        )

        self._workflows.remove(
            args.name,
            project_id=project_id,
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

        project_id = self._project_id(
            "workflows.read",
        )

        workflows = self._workflows.list(
            project_id=project_id,
        )

        emit(
            self._context,
            args,
            title="Registered Workflows",
            columns=[
                ("name", lambda w: w.name, False),
                ("version", lambda w: w.version, False),
                ("description", lambda w: w.description or "", False),
                ("created", lambda w: when(w.created_at.isoformat()), True),
                ("updated", lambda w: when(w.updated_at.isoformat()), False),
            ],
            items=workflows,
            kind="workflow",
            data=[
                {
                    "name": w.name,
                    "version": w.version,
                    "description": w.description,
                    "created_at": w.created_at.isoformat(),
                    "updated_at": w.updated_at.isoformat(),
                }
                for w in workflows
            ],
        )

    def _show(
        self,
        args: Namespace,
    ) -> None:
        """
        Show a registered workflow.
        """

        project_id = self._project_id(
            "workflows.read",
        )

        workflow = self._workflows.get(
            args.name,
            project_id=project_id,
        )

        mode = "json" if args.json else "yaml" if args.yaml else output_mode(self._context, args)

        if mode in ("json", "yaml"):

            self._context.ui.text(
                self._workflows.serialize(
                    workflow,
                    mode,
                ).rstrip("\n"),
            )

            return

        if mode != "detailed":

            emit(
                self._context,
                args,
                title="Workflow",
                columns=[
                    ("name", lambda w: w.name, False),
                    ("version", lambda w: w.version, False),
                    ("steps", lambda w: w.step_count, False),
                    ("description", lambda w: w.description or "", True),
                ],
                items=[workflow],
                kind="workflow",
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

        project_id = self._project_id(
            "workflows.write",
        )

        workflow = self._workflows.replace(
            args.name,
            args.from_file,
            project_id=project_id,
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

        project_id = self._project_id(
            "workflows.write",
        )

        result = self._workflows.edit(
            args.name,
            project_id=project_id,
        )

        if result.changed:

            self._context.ui.success(
                f"Workflow '{result.workflow.name}' " "updated successfully.",
            )

        else:

            self._context.ui.info(
                f"Workflow '{result.workflow.name}' " "was not changed.",
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

    def _execution_options(
        self,
        args: Namespace,
    ) -> WorkflowExecutionOptions:
        """
        Build workflow execution options from CLI arguments.
        """

        tags = tuple(tag.strip() for tag in (args.tags or "").split(",") if tag.strip())

        variables, step_overrides = self._argument_overrides(
            args,
        )

        return WorkflowExecutionOptions(
            tags=tags,
            from_step=args.from_step,
            to_step=args.to_step,
            skip_steps=tuple(step.strip() for step in args.skip_steps if step.strip()),
            dry_run=args.dry_run,
            variables=variables,
            step_overrides=step_overrides,
        )

    def _start_execution_options(
        self,
        args: Namespace,
    ) -> WorkflowExecutionOptions:
        """
        Build execution options for a background workflow.
        """

        tags = tuple(tag.strip() for tag in (args.tags or "").split(",") if tag.strip())

        variables, step_overrides = self._argument_overrides(
            args,
        )

        return WorkflowExecutionOptions(
            tags=tags,
            from_step=args.from_step,
            to_step=args.to_step,
            skip_steps=tuple(step.strip() for step in args.skip_steps if step.strip()),
            dry_run=False,
            variables=variables,
            step_overrides=step_overrides,
        )

    def _argument_overrides(
        self,
        args: Namespace,
    ) -> tuple[
        dict[str, object],
        dict[str, dict[str, object]],
    ]:
        """
        Parse workflow variable and step argument overrides.
        """

        variables = self._assignments.parse(
            args.arguments,
            separator=args.separator,
        )

        assignments = self._assignments.parse_typed(
            args.set,
            separator=args.separator,
            value_type=args.type,
        )

        step_overrides: dict[str, dict[str, object]] = {}

        for key, value in assignments.items():

            if "." not in key:

                raise WorkflowArgumentError(
                    f"Invalid step override '{key}'. " "Expected STEP.KEY=VALUE.",
                )

            step_name, argument_name = key.split(
                ".",
                1,
            )

            if not step_name or not argument_name:

                raise WorkflowArgumentError(
                    f"Invalid step override '{key}'. " "Expected STEP.KEY=VALUE.",
                )

            step_overrides.setdefault(
                step_name,
                {},
            )[argument_name] = value

        return (
            variables,
            step_overrides,
        )

    def _require(
        self,
        permission: str,
        project_id: int | None = None,
    ) -> None:

        session = self._session.require()

        if project_id is None:
            self._authorization.require(session, permission)
        elif not self._authorization.has_permission(session.user_id, permission, project_id):
            raise AuthorizationRequiredError(permission)

    def _project_id(self, permission: str) -> int:
        """
        The selected project, after checking `permission` in it. Registered
        workflows are project scoped, so names are looked up there.
        """

        session = self._session.require()
        project = ProjectContext(self._context).current(session)
        self._require(permission, project["id"])
        return int(project["id"])

    def _record_cli_run(self, job_id: int, target: str, project_id: int) -> None:
        assert self._context.database_manager is not None
        store = RunStore(self._context.database_manager.connection)
        store.record(
            job_id,
            node="local",
            kind="workflow",
            target=target,
            trigger="manual",
        )
        store.set_project(job_id, project_id)
