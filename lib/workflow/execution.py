"""
Workflow execution engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.runtime.execution import WorkflowExecution
from lib.models.workflow import FailurePolicy
from lib.workflow.exceptions import WorkflowExecutionError

if TYPE_CHECKING:
    from core.context import EntropyContext
    from lib.models.workflow import WorkflowDefinition, WorkflowStep


class WorkflowExecutor:
    """
    Executes workflow definitions.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        self._context = context

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def execute(
        self,
        workflow: WorkflowDefinition,
    ) -> WorkflowExecution:
        """
        Execute a workflow.
        """

        assert self._context.execution_manager is not None
        assert self._context.plugin_manager is not None

        execution = self._context.execution_manager.create(
            workflow,
        )

        try:

            for step in sorted(
                workflow.steps,
                key=lambda item: item.order,
            ):

                if not step.policy.enabled:

                    continue

                self._execute_step(
                    execution,
                    step,
                )

            execution.complete()

        except Exception:

            execution.fail()

            raise

        return execution

    # ------------------------------------------------------------------
    # Step
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        execution: WorkflowExecution,
        step: WorkflowStep,
    ) -> None:

        try:

            assert self._context.plugin_manager is not None

            plugin = self._context.plugin_manager.load(
                step.plugin,
            )

            with execution.context.stage(
                name=step.name,
                metadata={
                    "step_id": step.id,
                    "plugin": step.plugin,
                },
            ):

                plugin.run(
                    execution.context,
                    step,
                )

        except Exception as exc:

            self._handle_failure(
                step,
                exc,
            )

    # ------------------------------------------------------------------
    # Failure
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_failure(
        step: WorkflowStep,
        cause: Exception,
    ) -> None:

        policy = step.policy.on_failure

        if policy is FailurePolicy.CONTINUE:
            return

        if policy is FailurePolicy.RETRY:
            raise NotImplementedError("Retry policy is not implemented.") from cause

        raise WorkflowExecutionError(f"Step '{step.name}' failed.") from cause
