"""
Workflow exceptions.
"""

from core.exceptions import EntropyException


class WorkflowStepExecutionError(EntropyException):

    def __init__(self, step, cause):

        self.step = step
        self.cause = cause

        message = (
            f"Workflow step '{step.id}' "
            f"({step.name}) failed."
        )

        super().__init__(message)
