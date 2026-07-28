"""
Workflow step executor.
"""

from lib.models.workflow import (
    FailurePolicy,
    WorkflowAction,
)

from .exceptions import WorkflowStepExecutionError


class StepExecutor:

    def __init__(self, context):

        self.context = context

        self._handlers = {

            FailurePolicy.ABORT:
                self._abort,

            FailurePolicy.CONTINUE:
                self._continue,

            FailurePolicy.ROLLBACK:
                self._rollback,

            FailurePolicy.SKIP_REMAINING:
                self._skip,
        }

    def execute(self, step):

        try:

            self._execute_retry(step)

        except Exception as exc:

            handler = self._handlers.get(
                step.on_failure,
                self._abort,
            )

            action = handler(
                step,
                exc,
            )

            if action is WorkflowAction.CONTINUE:
                return

            raise

    def _execute_retry(self, step):

        attempts = step.retry_count + 1

        last = None

        for attempt in range(1, attempts + 1):

            try:

                self.context.plugin_manager.execute(
                    step.plugin,
                    step.config,
                )

                return

            except Exception as exc:

                last = exc

                if attempt < attempts:

                    self.context.output.system.warning(
                        f"Retry {attempt}/{step.retry_count}"
                    )

        raise WorkflowStepExecutionError(
            step,
            last,
        )

    def _continue(self, step, exc):

        self.context.output.system.warning(
            f"Continuing after '{step.id}'"
        )

        return WorkflowAction.CONTINUE

    def _abort(self, step, exc):

        raise exc

    def _rollback(self, step, exc):

        #
        # TODO
        #

        return WorkflowAction.ABORT_WORKFLOW

    def _skip(self, step, exc):

        return WorkflowAction.ABORT_WORKFLOW