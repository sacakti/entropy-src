"""
Workflow stage.
"""

from __future__ import annotations

from lib.models.runtime import RuntimeNodeType
from core.models.enums import EventType

from .scope import ExecutionScope


class Stage(ExecutionScope):
    """
    Workflow execution stage.
    """

    @property
    def node_type(self) -> RuntimeNodeType:

        return RuntimeNodeType.STAGE

    @property
    def source(self) -> str:

        return "workflow"

    @property
    def started_event(self) -> EventType:

        return EventType.STAGE_STARTED

    @property
    def completed_event(self) -> EventType:

        return EventType.STAGE_COMPLETED

    @property
    def failed_event(self) -> EventType:

        return EventType.STAGE_FAILED
