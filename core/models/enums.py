"""
Observability enumerations.
"""

from enum import Enum


class EventType(str, Enum):
    """
    Runtime lifecycle events.
    """

    # ---------------------------------------------------------
    # Workflow
    # ---------------------------------------------------------

    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_CANCELLED = "execution.cancelled"

    # ---------------------------------------------------------
    # Step
    # ---------------------------------------------------------

    STEP_STARTED = "step.started"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"
    STEP_SKIPPED = "step.skipped"

    # ---------------------------------------------------------
    # Stage
    # ---------------------------------------------------------

    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"
    STAGE_CANCELLED ="stage.cancelled"

    # ---------------------------------------------------------
    # Activity
    # ---------------------------------------------------------

    ACTIVITY_STARTED = "activity.started"
    ACTIVITY_COMPLETED = "activity.completed"
    ACTIVITY_FAILED = "activity.failed"
    ACTIVITY_CANCELLED ="activity.cancelled"
