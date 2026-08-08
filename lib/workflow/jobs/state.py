"""
Workflow job states.
"""

from __future__ import annotations

from enum import Enum


class JobState(str, Enum):
    """
    Persistent state of a workflow job.
    """

    QUEUED = "queued"

    STARTING = "starting"

    RUNNING = "running"

    PAUSED = "paused"

    COMPLETED = "completed"

    FAILED = "failed"

    CANCELLED = "cancelled"
