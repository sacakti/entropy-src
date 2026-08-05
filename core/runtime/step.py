"""
Workflow step execution scope.
"""

from __future__ import annotations

from core.models.enums import EventType
from core.models.runtime import RuntimeNodeType

from .scope import ExecutionScope


class StepScope(
    ExecutionScope,
):
    """
    Runtime workflow step scope.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def node_type(
        self,
    ) -> RuntimeNodeType:

        return RuntimeNodeType.STEP

    @property
    def source(
        self,
    ) -> str:
        """
        Event source.
        """

        return "workflow"

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    @property
    def started_event(
        self,
    ) -> EventType:

        return EventType.STEP_STARTED

    @property
    def completed_event(
        self,
    ) -> EventType:

        return EventType.STEP_COMPLETED

    @property
    def failed_event(
        self,
    ) -> EventType:

        return EventType.STEP_FAILED

    @property
    def cancelled_event(
        self,
    ) -> EventType:

        return EventType.STEP_SKIPPED
