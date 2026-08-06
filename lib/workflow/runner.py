"""
Workflow runner.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from core.runtime.context import ExecutionContext

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

        runtime.start(
            workflow,
        )

        #
        # Enabled steps
        #

        enabled_steps = [
            step
            for step in workflow.steps
            if step.enabled
        ]

        total_steps = len(
            enabled_steps,
        )

        #
        # Execute workflow
        #

        with runtime.workflow(
            workflow.name,
        ):

            for index, step in enumerate(
                enabled_steps,
                start=1,
            ):

                with runtime.step(
                    step.name,
                    index=index,
                    total=total_steps,
                ):

                    self._initialize(
                        runtime,
                        workflow,
                        step,
                    )

                    self._execute(
                        runtime,
                        workflow,
                        step,
                    )

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
