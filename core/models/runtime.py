"""
Runtime models.
"""

from __future__ import annotations

from enum import Enum


# ----------------------------------------------------------------------
# Runtime Node
# ----------------------------------------------------------------------


class RuntimeNodeType(str, Enum):
    """
    Runtime execution hierarchy.
    """

    WORKFLOW = "workflow"

    STEP = "step"

    STAGE = "stage"

    ACTIVITY = "activity"

    CHECKPOINT = "checkpoint"

    GROUP = "group"


# ----------------------------------------------------------------------
# Runtime Lifecycle
# ----------------------------------------------------------------------


class ExecutionStatus(str, Enum):
    """
    Generic execution lifecycle.

    Used by every RuntimeNode.
    """

    CREATED = "created"

    RUNNING = "running"

    COMPLETED = "completed"

    FAILED = "failed"

    CANCELLED = "cancelled"


# ----------------------------------------------------------------------
# Failure Policy
# ----------------------------------------------------------------------


class FailurePolicy(str, Enum):
    """
    Runtime failure handling policy.
    """

    ABORT = "abort"

    CONTINUE = "continue"

    RETRY = "retry"

    ROLLBACK = "rollback"
