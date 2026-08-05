"""
Workflow exceptions.
"""

from core.exceptions import EntropyException


class WorkflowError(
    EntropyException,
):
    """
    Base workflow exception.
    """


class WorkflowNotFoundError(
    WorkflowError,
):
    """
    Workflow file not found.
    """

    def __init__(
        self,
        workflow,
    ) -> None:

        super().__init__(
            f"Workflow '{workflow}' does not exist.",
        )


class InvalidWorkflowError(
    WorkflowError,
):
    """
    Invalid workflow definition.
    """
