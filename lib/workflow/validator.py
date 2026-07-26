"""
Workflow validator.
"""

from __future__ import annotations


class WorkflowValidator:

    REQUIRED = (
        "name",
        "version",
        "steps",
    )

    STEP_REQUIRED = (
        "order",
        "id",
        "name",
        "plugin",
        "enabled",
    )

    def __init__(self, context):

        self.context = context

    def validate(self, workflow):

        task = self.context.output.progress(
            f"Validating workflow '{workflow['name']}'"
        )

        #
        # Mandatory keys
        #
        for key in self.REQUIRED:

            if key not in workflow:

                self.context.output.workflow.error(
                    f"Missing '{key}'",
                    task=task,
                )

                raise ValueError(
                    f"Missing workflow key '{key}'"
                )

        #
        # Validate steps
        #
        orders = set()

        for step in workflow["steps"]:

            for key in self.STEP_REQUIRED:

                if key not in step:

                    raise ValueError(
                        f"Step missing '{key}'"
                    )

            if step["order"] in orders:

                raise ValueError(
                    f"Duplicate order {step['order']}"
                )

            orders.add(step["order"])

        self.context.output.workflow.success(
            "Workflow validation successful",
            task=task,
        )

        self.context.output.workflow.info(
            f"Workflow contains {len(workflow['steps'])} steps"
        )