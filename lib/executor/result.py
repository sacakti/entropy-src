"""
Execution Result

Represents the outcome of an operating system command executed by the
LinuxExecutor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """
    Represents the result of a command execution.

    Attributes
    ----------
    command:
        The complete command that was executed.

    success:
        True when the command completed successfully
        (exit code == 0).

    exit_code:
        The operating system exit code returned by the process.

    stdout:
        Standard output captured from the process.

    stderr:
        Standard error captured from the process.

    duration:
        Execution time in seconds.
    """

    command: str

    success: bool

    exit_code: int

    stdout: str

    stderr: str

    duration: float

    @property
    def failed(self) -> bool:
        """
        Return True when the command execution failed.
        """
        return not self.success

    def __bool__(self) -> bool:
        """
        Allow the result object to be evaluated directly.

        Example
        -------
        >>> result = executor.run(["ls"])
        >>> if result:
        ...     print("Success")
        """
        return self.success

    def __str__(self) -> str:
        """
        Return a readable representation of the execution result.
        """
        status = "SUCCESS" if self.success else "FAILED"

        return f"{status} " f"(exit_code={self.exit_code}, " f"duration={self.duration:.3f}s)"
