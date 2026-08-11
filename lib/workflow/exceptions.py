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


class WorkflowCancelledError(
    WorkflowError,
):
    """
    Raised when a workflow is cancelled by the user.
    """

class WorkflowProcessNotRunningError(
    WorkflowError,
):
    """
    Raised when job is not running.
    """

    def __init__(
        self,
        pid: str,
    ) -> None:

        super().__init__(
            f"PID '{pid}' is not running.",
        )

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

class WorkflowNotMatchError(
    WorkflowError,
):
    def __init__(
            self,
            workflow_name: str,
            name: str
        ) -> None:

            super().__init__(
                f"Workflow name '{workflow_name}' "
                f"does not match registered workflow '{name}'.",
            )

class WorkflowAlreadyExistsError(
    WorkflowError,
):
    """
    Raised when attempting to add an already registered workflow.
    """

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Workflow '{name}' already exists.",
        )

class WorkflowJobNotRunningError(
    WorkflowError,
):
    """
    Raised when job is not running.
    """

    def __init__(
        self,
        job_id: str,
    ) -> None:

        super().__init__(
            f"Job '{job_id}' is not running.",
        )

class WorkflowJobIsNotPausedError(
    WorkflowError,
):
    """
    Raised when job is not paused.
    """

    def __init__(
        self,
        job_id: str,
    ) -> None:

        super().__init__(
            f"Job '{job_id}' is not paused.",
        )

class WorkflowInvalidTransitionError(
    WorkflowError,
):
    """
    Raised when job transition is invalid.
    """

    def __init__(
        self,
        current_state,
        target_state,
    ) -> None:

        super().__init__(
            f"Invalid workflow job transition: " f"'{current_state}' -> '{target_state}'.",
        )

class WorkflowNotQueuedError(
    WorkflowError,
):
    """
    Raised when workflow is not queued.
    """

    def __init__(
        self,
        job_id: int,
    ) -> None:

        super().__init__(
            f"Workflow job '{job_id}' is not queued.",
        )

class WorkflowProcessIDError(
    WorkflowError,
):
    """
    Raised when workflow is not queued.
    """

    def __init__(
        self,
    ) -> None:

        super().__init__(
            "Process ID must be greater than zero.",
        )

class WorkflowFileRequiredError(
    WorkflowError,
):
    """
    Raised when workflow is not queued.
    """

    def __init__(
        self,
    ) -> None:

        super().__init__(
            "Either a workflow name or workflow file is required.",
        )

class WorkflowTooManyFilesError(
    WorkflowError,
):
    """
    Raised when workflow is not queued.
    """

    def __init__(
        self,
    ) -> None:

        super().__init__(
            "Specify either a workflow name or a workflow file, "
            "not both.",
        )

class WorkflowInvalidProvidedError(
    WorkflowError,
):
    """
    Raised when workflow is not queued.
    """

    def __init__(
        self,
    ) -> None:

        super().__init__(
            "Specify a workflow name or a workflow file.",
        )

class WorkflowFormatError(
    WorkflowError,
):
    """
    Raised when a workflow format or file extension is unsupported.
    """


class WorkflowJobIDRequiredError(
    WorkflowError,
):
    """
    Raised when a persisted workflow job ID is required.
    """

    def __init__(
        self,
    ) -> None:

        super().__init__(
            "Workflow job has not been persisted.",
        )

class WorkflowFileError(
    WorkflowError,
):
    """
    Raised when a workflow definition file cannot be accessed.
    """


class WorkflowFileNotFoundError(
    WorkflowFileError,
):
    """
    Raised when a workflow definition file does not exist.
    """

    def __init__(
        self,
        path,
    ) -> None:

        super().__init__(
            f"Workflow file not found: {path}",
        )


class WorkflowFileReadError(
    WorkflowFileError,
):
    """
    Raised when a workflow definition file cannot be read.
    """

    def __init__(
        self,
        path,
    ) -> None:

        super().__init__(
            f"Unable to read workflow file '{path}'.",
        )


class WorkflowFileWriteError(
    WorkflowFileError,
):
    """
    Raised when a workflow definition file cannot be written.
    """

    def __init__(
        self,
        path,
    ) -> None:

        super().__init__(
            f"Unable to write workflow file '{path}'.",
        )


class WorkflowPathNotFileError(
    WorkflowFileError,
):
    """
    Raised when a workflow path does not point to a file.
    """

    def __init__(
        self,
        path,
    ) -> None:

        super().__init__(
            f"Workflow path is not a file: {path}",
        )

class WorkflowInvalidTerminalError(
    WorkflowFileError,
):
    """
    Raised when a workflow terminal state is invalid.
    """

    def __init__(
        self,
        state,
    ) -> None:

        super().__init__(
           f"Invalid terminal state '{state}'.",
        )
