"""
Workflow validator.
"""

from lib.models.workflow import WorkflowDefinition


class WorkflowValidator:

    def validate(
        self,
        workflow: WorkflowDefinition,
    ):

        errors = []

        if not workflow.name:
            errors.append("Workflow name is required.")

        if not workflow.version:
            errors.append("Workflow version is required.")

        orders = set()

        for step in workflow.steps:

            if step.order in orders:

                errors.append(
                    f"Duplicate step order {step.order}"
                )

            orders.add(step.order)

        if errors:

            raise ValueError(
                "\n".join(errors)
            )
