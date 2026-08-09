"""
Workflow manager.
"""

from __future__ import annotations

from pathlib import Path

from core.context import EntropyContext
from core.ui import UIManager

from lib.models.workflow import Workflow
from lib.workflow.jobs.model import WorkflowJob

from .loader import WorkflowLoader
from .validator import WorkflowValidator
from .follower import WorkflowFollower
from .renderer import WorkflowEventRenderer
from .process import WorkflowProcess

class WorkflowManager:
    """
    Coordinates workflow lifecycle.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.plugin_manager is not None

        self._context = context

        self._loader = WorkflowLoader(
            context,
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
        Load a workflow definition.
        """

        workflow = self._loader.load(
            file,
        )

        self._validator.validate(
            workflow,
        )

        return workflow

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        workflow: Workflow,
        *,
        execution=None,
        job_id: int | None = None,
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
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        file: Path,
        *,
        execution=None,
        job_id: int | None = None,
    ) -> None:
        """
        Load and execute a workflow.

        An existing execution may be supplied by the
        background-job subsystem.
        """

        workflow = self.load(
            file,
        )

        self.execute(
            workflow,
            execution=execution,
            job_id=job_id,
        )

    # ------------------------------------------------------------------
    # Start a background process
    # ------------------------------------------------------------------

    def start(
        self,
        file: Path,
    ) -> WorkflowJob:
        """
        Start a workflow in a background process.

        The persistent workflow job is created before the worker
        process is started so the worker can attach to it.
        """

        workflow = self.load(
            file,
        )

        assert self._context.workflow_job_manager is not None
        assert self._context.execution_manager is not None

        execution = self._context.execution_manager.create(
            workflow,
        )

        job = self._context.workflow_job_manager.create(
            execution_id=execution.id,
            workflow=workflow.name,
            workspace=execution.context.workspace,
            pid=0,
        )

        assert self._context.bootstrap is not None
        assert self._context.paths is not None

        process = WorkflowProcess(
            job_id=job.id,
            workflow=file,
            project_root=self._context.bootstrap.project_root,
            python_packages=self._context.paths.python.packages,
        )

        pid = process.start()

        self._context.workflow_job_manager.set_pid(
            job.id,
            pid,
        )

        return self._context.workflow_job_manager.get(
            job.id,
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
