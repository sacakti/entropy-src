"""
Workflow runner.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from core.runtime.context import ExecutionContext
from core.runtime.execution import WorkflowExecution

from lib.models.workflow import (
    Workflow,
    WorkflowStep,
)

if TYPE_CHECKING:
    from core.context import EntropyContext
    from lib.plugins.runner import PluginRunner


class WorkflowRunner:
    """
    Executes workflows.
    """

    def __init__(
        self,
        context: EntropyContext,
        plugin_runner: PluginRunner,
    ) -> None:

        self._context = context
        self._plugins = plugin_runner

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        workflow: Workflow,
    ) -> None:
        """
        Execute a workflow.
        """

        assert self._context.paths is not None
        assert self._context.executor is not None

        #
        # Create execution workspace.
        #

        workspace = (
            self._context.paths.workflow.directory
            / (
                f"{datetime.now():%Y%m%d_%H%M%S}_"
                f"{workflow.name.lower().replace(' ', '_')}"
            )
        )

        self._context.executor.mkdir(
            workspace,
        )

        #
        # Runtime
        #

        runtime = ExecutionContext(
            entropy=self._context,
            workspace=workspace,
        )

        runtime.set_variables(
            workflow.variables,
        )

        runtime.execution = WorkflowExecution(
            id=uuid4().hex,
            workflow=workflow,
            context=runtime,
        )

        #
        # Workflow
        #

        with runtime.workflow(
            workflow.name,
        ):

            for step in workflow.steps:

                if not step.enabled:

                    continue

                with runtime.step(
                    step.name,
                ):

                    self._run_step(
                        runtime,
                        workflow,
                        step,
                    )

    # ------------------------------------------------------------------
    # Step
    # ------------------------------------------------------------------

    def _run_step(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
    ) -> None:
        """
        Execute a workflow step.
        """

        with runtime.stage(
            name="Initialize",
        ):

            self._initialize(
                runtime,
                workflow,
                step,
            )

        with runtime.stage(
            name="Execute",
        ):

            self._execute(
                runtime,
                workflow,
                step,
            )

        with runtime.stage(
            name="Finalize",
        ):

            self._finalize(
                runtime,
                workflow,
                step,
            )

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    def _initialize(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
    ) -> None:
        """
        Prepare step execution.
        """

        runtime.set_arguments(
            step.arguments,
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def _execute(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
    ) -> None:
        """
        Execute the workflow plugin.
        """

        self._plugins.execute(
            context=runtime,
            qualified_name=step.plugin,
        )

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    def _finalize(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
    ) -> None:
        """
        Finalize step execution.
        """

        pass
