"""
Workflow validator.
"""

from __future__ import annotations

from .exceptions import WorkflowValidationError
from lib.models.workflow import WorkflowDefinition


class WorkflowValidator:
    """
    Validates workflow definitions.
    """

    def validate(
        self,
        workflow: WorkflowDefinition,
    ) -> None:

        errors: list[str] = []

        #
        # Workflow
        #

        if not workflow.name:

            errors.append(
                "Workflow name is required."
            )

        if not workflow.steps:

            errors.append(
                "Workflow must contain at least one step."
            )

        #
        # Step ids
        #

        ids: set[str] = set()

        for step in workflow.steps:

            if not step.id:

                errors.append(
                    "Step id is required."
                )

            elif step.id in ids:

                errors.append(
                    f"Duplicate step id '{step.id}'."
                )

            ids.add(step.id)

        #
        # Execution order
        #

        orders: set[int] = set()

        for step in workflow.steps:

            if step.order in orders:

                errors.append(
                    f"Duplicate step order '{step.order}'."
                )

            orders.add(step.order)

        #
        # Plugin
        #

        for step in workflow.steps:

            if not step.plugin:

                errors.append(
                    f"Step '{step.name}' does not specify a plugin."
                )

        #
        # Retry
        #

        for step in workflow.steps:

            if step.policy.retries < 0:

                errors.append(
                    f"Step '{step.name}' has an invalid retry count."
                )

        #
        # Timeout
        #

        for step in workflow.steps:

            timeout = step.policy.timeout

            if (
                timeout is not None
                and timeout <= 0
            ):

                errors.append(
                    f"Step '{step.name}' has an invalid timeout."
                )

        if errors:

            raise WorkflowValidationError(
                errors,
            )
