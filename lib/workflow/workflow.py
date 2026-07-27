"""
Workflow loader.
"""

from __future__ import annotations

import json

from core.constants import WORKFLOW_DIR
from lib.models.workflow import (
    FailurePolicy,
    WorkflowAction,
    WorkflowDefinition,
    WorkflowStep,
)
from lib.workflow.exceptions import WorkflowStepExecutionError
from lib.workflow.validator import WorkflowValidator


class Workflow:

    def __init__(self, context):

        self.context = context
        self.data = None

        self._failure_handlers = {
            FailurePolicy.ABORT: self._handle_abort,
            FailurePolicy.CONTINUE: self._handle_continue,
            FailurePolicy.ROLLBACK: self._handle_rollback,
            FailurePolicy.SKIP_REMAINING: self._handle_skip_remaining,
        }

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    def load(self, workflow_name: str):

        workflow_file = WORKFLOW_DIR / f"{workflow_name}.json"

        task = self.context.output.progress(
            f"Loading workflow '{workflow_name}'"
        )

        if not workflow_file.exists():

            self.context.output.workflow.error(
                f"Workflow '{workflow_name}' not found",
                task=task,
            )

            raise FileNotFoundError(workflow_file)

        with workflow_file.open(
            "r",
            encoding="utf-8",
        ) as fp:

            raw = json.load(fp)

        self.context.output.workflow.success(
            f"Workflow '{workflow_name}' loaded",
            task=task,
        )

        validator = WorkflowValidator(self.context)

        validator.validate(raw)

        workflow = WorkflowDefinition(
            name=raw["name"],
            version=raw["version"],
            steps=[
                WorkflowStep(
                    order=step["order"],
                    id=step["id"],
                    name=step["name"],
                    plugin=step["plugin"],
                    enabled=step.get("enabled", True),
                    config=step.get("config", {}),
                    retry_count=step.get("retry_count", 0),
                    on_failure=FailurePolicy(
                        step.get("on_failure", "abort")
                    ),
                )
                for step in raw["steps"]
            ],
        )

        workflow.steps.sort(key=lambda step: step.order)

        self.data = workflow
        self.context.workflow = workflow

        return workflow

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    def execute(self):

        for step in self.data.steps:

            if not step.enabled:
                continue

            self.context.output.step(
                step.order,
                step.name,
            )

            try:

                self._execute_with_retry(step)

            except Exception as exc:

                handler = self._failure_handlers.get(
                    step.on_failure,
                    self._handle_abort,
                )

                action = handler(step, exc)

                if action is WorkflowAction.CONTINUE:
                    continue

                if action is WorkflowAction.ABORT_WORKFLOW:
                    break

    # ------------------------------------------------------------------ #
    # Step execution
    # ------------------------------------------------------------------ #

    def _execute_step(self, step):

        self.context.plugin_manager.execute(
            step.plugin,
            step.config,
        )

    def _execute_with_retry(self, step):

        attempts = step.retry_count + 1

        last_exception = None

        for attempt in range(1, attempts + 1):

            try:

                self._execute_step(step)

                return

            except Exception as exc:

                last_exception = exc

                self.context.output.workflow.error(
                    str(exc)
                )

                if attempt < attempts:

                    self.context.output.system.warning(
                        f"Retrying ({attempt}/{step.retry_count})..."
                    )

        raise WorkflowStepExecutionError(
            step,
            last_exception,
        ) from last_exception

    # ------------------------------------------------------------------ #
    # Failure handlers
    # ------------------------------------------------------------------ #

    def _handle_continue(self, step, exc):

        self.context.output.system.warning(
            f"Step '{step.id}' failed. Continuing workflow."
        )

        return WorkflowAction.CONTINUE

    def _handle_abort(self, step, exc):

        raise exc

    def _handle_rollback(self, step, exc):

        self.context.output.system.warning(
            f"Step '{step.id}' failed. Rolling back deployment."
        )

        #
        # TODO:
        # Invoke rollback manager
        #

        return WorkflowAction.ABORT_WORKFLOW

    def _handle_skip_remaining(self, step, exc):

        self.context.output.system.warning(
            f"Skipping remaining workflow steps."
        )

        return WorkflowAction.ABORT_WORKFLOW