"""
Workflow execution model.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from core.models.runtime import ExecutionStatus

if TYPE_CHECKING:
    from .context import ExecutionContext


@dataclass
class WorkflowExecution:
    """
    Represents a single workflow execution.

    Owns the lifecycle of a workflow execution.

    This class does not execute workflows. It only
    maintains runtime state.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    id: str

    workflow: Any

    context: ExecutionContext

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    status: ExecutionStatus = ExecutionStatus.CREATED

    started_at: datetime | None = None

    finished_at: datetime | None = None

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Mark execution as started.
        """

        self.status = ExecutionStatus.RUNNING

        if self.started_at is None:

            self.started_at = datetime.utcnow()

    def complete(self) -> None:
        """
        Mark execution as completed.
        """

        self.status = ExecutionStatus.COMPLETED

        if self.finished_at is None:

            self.finished_at = datetime.utcnow()

    def fail(self) -> None:
        """
        Mark execution as failed.
        """

        self.status = ExecutionStatus.FAILED

        if self.finished_at is None:

            self.finished_at = datetime.utcnow()

    def cancel(self) -> None:
        """
        Mark execution as cancelled.
        """

        self.status = ExecutionStatus.CANCELLED

        if self.finished_at is None:

            self.finished_at = datetime.utcnow()

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def put(
        self,
        key: str,
        value: Any,
    ) -> None:
        """
        Store a metadata value.
        """

        self.metadata[key] = value

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Retrieve a metadata value.
        """

        return self.metadata.get(
            key,
            default,
        )

    def update(
        self,
        **kwargs: Any,
    ) -> None:
        """
        Update multiple metadata values.
        """

        self.metadata.update(kwargs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def duration_ms(self) -> int | None:
        """
        Execution duration in milliseconds.
        """

        if self.started_at is None:

            return None

        end = self.finished_at or datetime.utcnow()

        return int(
            (end - self.started_at).total_seconds() * 1000
        )

    @property
    def running(self) -> bool:
        """
        True if execution is currently running.
        """

        return self.status is ExecutionStatus.RUNNING

    @property
    def succeeded(self) -> bool:
        """
        True if execution completed successfully.
        """

        return self.status is ExecutionStatus.COMPLETED

    @property
    def failed(self) -> bool:
        """
        True if execution failed.
        """

        return self.status is ExecutionStatus.FAILED

    @property
    def cancelled(self) -> bool:
        """
        True if execution was cancelled.
        """

        return self.status is ExecutionStatus.CANCELLED

    @property
    def finished(self) -> bool:
        """
        True if execution has finished.
        """

        return self.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        )

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __str__(self) -> str:

        return self.id

    def __repr__(self) -> str:

        return (
            "WorkflowExecution("
            f"id={self.id!r}, "
            f"status={self.status.value!r})"
        )
