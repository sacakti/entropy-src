"""
Workflow manager.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.context import EntropyContext
from lib.database.repositories.workflow_registry import WorkflowRegistryRepository
from lib.models.workflow import Workflow, WorkflowEditResult, WorkflowExecutionOptions
from lib.workflow.exceptions import (
    WorkflowAlreadyExistsError,
    WorkflowInvalidProvidedError,
    WorkflowNotFoundError,
    WorkflowNotMatchError,
    WorkflowTooManyFilesError,
)
from lib.workflow.jobs.model import WorkflowJob

from .follower import WorkflowFollower
from .loader import WorkflowLoader
from .process import WorkflowProcess
from .renderer import WorkflowEventRenderer
from .validator import WorkflowValidator


class WorkflowManager:
    """
    Coordinates workflow lifecycle.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.plugin_manager is not None
        assert context.database_manager is not None
        assert context.executor is not None

        self._context = context

        self._loader = WorkflowLoader(
            context,
        )

        self._registry = WorkflowRegistryRepository(
            context.database_manager.connection,
        )

        self._validator = WorkflowValidator(
            context.plugin_manager,
        )

        assert context.workflow_runner is not None

        self._runner = context.workflow_runner

        assert context.workflow_job_manager is not None
        assert context.ui is not None

        self._jobs = context.workflow_job_manager

        self._follower = WorkflowFollower(
            jobs=self._jobs,
            renderer=WorkflowEventRenderer(
                context.ui,
            ),
        )

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(
        self,
        file: Path,
    ) -> Workflow:
        """
        Load and validate a workflow definition.
        """

        workflow = self._loader.load(
            file,
        )

        self._validator.validate(
            workflow,
        )

        return workflow

    def resolve(
        self,
        file: Path,
    ) -> Path:
        """
        Resolve a workflow definition path.

        Relative paths are resolved against the configured
        workspace workflow directory.

        Absolute paths are used as supplied.
        """

        file = file.expanduser()

        if file.is_absolute():
            return file

        assert self._context.paths is not None

        workspace_file = self._context.paths.workspace.workflows / file

        if workspace_file.exists():
            return workspace_file

        return file

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        workflow: Workflow,
        *,
        execution=None,
        job_id: int | None = None,
        options: WorkflowExecutionOptions | None = None,
    ) -> None:
        """
        Execute a validated workflow.

        An existing execution may be supplied by the
        background-job subsystem.
        """

        self._runner.execute(
            workflow,
            job_id=job_id,
            execution=execution,
            options=options,
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        name: str | None = None,
        *,
        file: Path | None = None,
        execution=None,
        job_id: int | None = None,
        options: WorkflowExecutionOptions | None = None,
    ) -> None:
        """
        Execute a registered workflow or workflow file.
        """

        if name is not None and file is not None:

            raise WorkflowTooManyFilesError()

        if name is None and file is None:

            raise WorkflowInvalidProvidedError()

        if name is not None:

            workflow = self.get(
                name,
            )

        else:

            assert file is not None

            workflow = self.load(
                self.resolve(
                    file,
                ),
            )

        self.execute(
            workflow,
            execution=execution,
            job_id=job_id,
            options=options,
        )

    # ------------------------------------------------------------------
    # Start a background process
    # ------------------------------------------------------------------

    def start(
        self,
        name: str | None = None,
        *,
        file: Path | None = None,
        options: WorkflowExecutionOptions | None = None,
    ) -> WorkflowJob:
        """
        Start a registered workflow or workflow file
        in the background.
        """

        if name is not None and file is not None:

            raise WorkflowTooManyFilesError

        if name is None and file is None:

            raise WorkflowInvalidProvidedError

        #
        # Resolve workflow.
        #

        if name is not None:

            workflow = self.get(
                name,
            )

            workflow_file = self._materialize(
                workflow,
            )

        else:

            assert file is not None

            workflow_file = self.resolve(
                file,
            )

            workflow = self.load(
                workflow_file,
            )

        #
        # Create execution.
        #

        if options is None:

            options = WorkflowExecutionOptions()

        assert self._context.workflow_job_manager is not None
        assert self._context.execution_manager is not None

        assert self._context.session_manager is not None

        session = self._context.session_manager.require()

        variables = dict(
            workflow.variables,
        )

        variables.update(
            options.variables,
        )

        execution = self._context.execution_manager.create(
            workflow,
            variables=variables,
        )

        job = self._context.workflow_job_manager.create(
            execution_id=execution.id,
            workflow=workflow.name,
            user_id=session.user_id,
            username=session.username,
            workspace=execution.context.workspace,
            pid=0,
        )

        #
        # Start background process.
        #

        assert self._context.bootstrap is not None
        assert self._context.paths is not None

        job_id = job.require_id()

        process = WorkflowProcess(
            job_id=job_id,
            workflow=workflow_file,
            worker=self._context.bootstrap.worker,
            project_root=self._context.bootstrap.project_root,
            python_packages=self._context.paths.python.packages,
            options=options,
        )

        pid = process.start()

        self._context.workflow_job_manager.set_pid(
            job_id,
            pid,
        )

        return self._context.workflow_job_manager.get(
            job_id,
        )

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def jobs(self) -> list[WorkflowJob]:

        assert self._context.workflow_job_manager is not None

        return self._context.workflow_job_manager.list()

    def job_by_pid(
        self,
        pid: int,
    ) -> WorkflowJob:

        assert self._context.workflow_job_manager is not None

        return self._context.workflow_job_manager.get_by_pid(
            pid,
        )

    def stop(
        self,
        pid: int,
    ) -> WorkflowJob:
        """
        Request graceful cancellation of a workflow by PID.
        """

        return self._jobs.stop(
            pid,
        )

    def follow(
        self,
        pid: int,
    ) -> None:
        """
        Follow a workflow execution by PID.
        """

        job = self.job_by_pid(
            pid,
        )

        self._follower.follow(
            job,
        )

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def serialize(
        self,
        workflow: Workflow,
        format: str = "json",
    ) -> str:
        """
        Serialize a workflow definition.

        The requested format is resolved through the
        workflow codec registry.
        """

        return self._serialize(
            workflow=workflow,
            format=format,
        )

    def deserialize(
        self,
        definition: str,
    ) -> Workflow:
        """
        Deserialize a stored workflow definition.

        Stored workflow definitions currently use JSON.
        """

        return self._deserialize(
            definition=definition,
        )

    def _serialize(
        self,
        workflow: Workflow,
        format: str = "json",
    ) -> str:
        """
        Serialize a workflow definition.
        """
        assert self._context.workflow_codecs is not None

        codec = self._context.workflow_codecs.get(
            format,
        )

        return codec.encode(
            workflow,
        )

    def _deserialize(
        self,
        definition: str,
    ) -> Workflow:
        """
        Deserialize a stored workflow definition.
        """

        assert self._context.workflow_codecs is not None

        return self._context.workflow_codecs.get(
            "json",
        ).decode(
            definition,
        )

    def add(
        self,
        file: Path,
    ) -> Workflow:
        """
        Load, validate and register a workflow definition.
        """

        file = self.resolve(
            file,
        )

        workflow = self.load(
            file,
        )

        if self._registry.exists(
            workflow.name,
        ):

            raise WorkflowAlreadyExistsError(
                workflow.name,
            )

        definition = self._serialize(
            workflow,
        )

        now = self._timestamp()

        self._registry.create(
            name=workflow.name,
            version=workflow.version,
            description=workflow.description,
            definition=definition,
            created_at=now,
            updated_at=now,
        )

        return workflow

    def remove(
        self,
        name: str,
    ) -> None:
        """
        Remove a registered workflow.
        """

        if not self._registry.exists(
            name,
        ):

            raise WorkflowNotFoundError(
                name,
            )

        self._registry.delete(
            name,
        )

    def replace(
        self,
        name: str,
        file: Path,
    ) -> Workflow:
        """
        Replace an existing registered workflow.
        """

        file = self.resolve(
            file,
        )

        workflow = self.load(
            file,
        )

        if workflow.name != name:

            raise WorkflowNotMatchError(
                workflow.name,
                name,
            )

        if not self._registry.exists(
            name,
        ):

            raise WorkflowNotFoundError(name)

        definition = self._serialize(
            workflow,
        )

        self._registry.update(
            name=name,
            version=workflow.version,
            description=workflow.description,
            definition=definition,
            updated_at=self._timestamp(),
        )

        return workflow

    def get(
        self,
        name: str,
    ) -> Workflow:
        """
        Return a registered workflow.
        """

        entry = self._registry.get_by_name(
            name,
        )

        if entry is None:

            raise WorkflowNotFoundError(
                name,
            )

        workflow = self._deserialize(
            entry.definition,
        )

        self._validator.validate(
            workflow,
        )

        return workflow

    def list(
        self,
    ):
        """
        Return registered workflow definitions.
        """

        return self._registry.list()

    def edit(
        self,
        name: str,
    ) -> WorkflowEditResult:
        """
        Edit a registered workflow interactively.
        """

        workflow = self.get(
            name,
        )

        original = self._serialize(
            workflow,
            format="json",
        )

        edited_definition = self._context.ui.editor(
            original,
            filename=f"{name}.json",
        )

        #
        # Editor exited without modifying the definition.
        #

        if edited_definition == original:

            return WorkflowEditResult(
                workflow=workflow,
                changed=False,
            )

        #
        # Decode the edited definition.
        #

        updated = self._deserialize(
            edited_definition,
        )

        #
        # Validate before modifying the database.
        #

        self._validator.validate(
            updated,
        )

        #
        # Workflow identity must remain unchanged.
        #

        if updated.name != name:

            raise WorkflowNotMatchError(
                updated.name,
                name,
            )

        #
        # Persist only after successful validation.
        #

        self._registry.update(
            name=name,
            version=updated.version,
            description=updated.description,
            definition=self._serialize(
                updated,
                format="json",
            ),
            updated_at=self._timestamp(),
        )

        return WorkflowEditResult(
            workflow=updated,
            changed=True,
        )

    # Helpers
    def _timestamp(
        self,
    ) -> str:
        """
        Return the current UTC timestamp.
        """

        return datetime.now(
            timezone.utc,
        ).isoformat()

    def _materialize(
        self,
        workflow: Workflow,
    ) -> Path:
        """
        Materialize a registered workflow definition for
        background execution.

        The SQLite registry remains the source of truth.
        """

        assert self._context.paths is not None
        assert self._context.workflow_codecs is not None

        directory = self._context.paths.workspace.workflows

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = directory / f"{workflow.name}.json"

        codec = self._context.workflow_codecs.get(
            "json",
        )

        codec.encode_file(
            workflow,
            path,
        )

        return path
