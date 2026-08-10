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


class WorkflowCancelledError(EntropyException):
    """
    Raised when a workflow is cancelled by the user.
    """


class WorkflowJobNotFoundError(
    WorkflowError,
):
    """
    Raised when a workflow job cannot be found.
    """

    def __init__(
        self,
        pid: int,
    ) -> None:

        super().__init__(
            f"Workflow process '{pid}' was not found.",
        )
