"""
Workflow executor.
"""

from .step_executor import StepExecutor


class WorkflowExecutor:

    def __init__(self, context):

        self.context = context

        self.step_executor = StepExecutor(
            context,
        )

    def execute(self, workflow):

        for step in workflow.steps:

            if not step.enabled:
                continue

            self.context.output.step(
                step.order,
                step.name,
            )

            self.step_executor.execute(step)