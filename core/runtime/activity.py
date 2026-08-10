"""
Workflow activity.
"""

from __future__ import annotations

from core.models.enums import EventType
from core.models.runtime import RuntimeNodeType

from .scope import ExecutionScope


class Activity(ExecutionScope):
    """
    Workflow execution activity.
    """

    @property
    def node_type(self) -> RuntimeNodeType:

        return RuntimeNodeType.ACTIVITY

    @property
    def source(self) -> str:

        return "workflow"

    @property
    def started_event(self) -> EventType:

        return EventType.ACTIVITY_STARTED

    @property
    def completed_event(self) -> EventType:

        return EventType.ACTIVITY_COMPLETED

    @property
    def failed_event(self) -> EventType:

        return EventType.ACTIVITY_FAILED

    @property
    def cancelled_event(self) -> EventType:

        return EventType.ACTIVITY_CANCELLED
