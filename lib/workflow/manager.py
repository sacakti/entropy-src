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
    ) -> None:
        """
        Execute a validated workflow.
        """

        self._runner.execute(
            workflow,
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        file: Path,
    ) -> None:
        """
        Load and execute a workflow.
        """

        workflow = self.load(
            file,
        )

        self.execute(
            workflow,
        )

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
