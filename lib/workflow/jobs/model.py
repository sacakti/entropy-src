"""
Workflow job models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .state import JobState


@dataclass
class WorkflowJob:
    """
    Persistent representation of a workflow execution job.
    """

    id: int | None

    execution_id: str

    workflow: str

    state: JobState

    pid: int | None

    workspace: Path

    created_at: datetime | None = None

    started_at: datetime | None = None

    finished_at: datetime | None = None

    exit_code: int | None = None

    @property
    def running(self) -> bool:
        """
        Return True if the job is currently active.
        """

        return self.state in (
            JobState.STARTING,
            JobState.RUNNING,
            JobState.PAUSED,
        )

    @property
    def finished(self) -> bool:
        """
        Return True if the job has finished.
        """

        return self.state in (
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.CANCELLED,
        )
