"""
Workflow manager.
"""

from __future__ import annotations

from pathlib import Path

from core.context import EntropyContext

from lib.models.workflow import Workflow

from .loader import WorkflowLoader
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

        self._context = context

        self._loader = WorkflowLoader(
            context,
        )

        self._validator = WorkflowValidator(
            context.plugin_manager,
        )

        assert context.workflow_runner is not None

        self._runner = context.workflow_runner

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
