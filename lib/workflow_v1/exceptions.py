"""
Workflow exceptions.
"""

from __future__ import annotations

from core.exceptions import EntropyException


class WorkflowError(EntropyException):
    """
    Base workflow exception.
    """


class WorkflowNotFoundError(WorkflowError):
    """
    Workflow not found.
    """

    def __init__(
        self,
        workflow: str,
    ) -> None:

        super().__init__(f"Workflow '{workflow}' was not found.")


class WorkflowValidationError(
    WorkflowError,
):
    """
    Workflow validation failed.
    """

    def __init__(
        self,
        errors: list[str],
    ) -> None:

        message = "Workflow validation failed:\n" + "\n".join(f"  • {error}" for error in errors)

        super().__init__(message)


class WorkflowExecutionError(
    WorkflowError,
):
    """
    Workflow execution failed.
    """

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(message)
