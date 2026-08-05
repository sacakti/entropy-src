"""
Workflow execution scope.
"""

from __future__ import annotations

from core.models.enums import EventType
from core.models.runtime import RuntimeNodeType

from .scope import ExecutionScope


class WorkflowScope(
    ExecutionScope,
):
    """
    Runtime workflow scope.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def node_type(
        self,
    ) -> RuntimeNodeType:

        return RuntimeNodeType.WORKFLOW

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

        return EventType.EXECUTION_STARTED

    @property
    def completed_event(
        self,
    ) -> EventType:

        return EventType.EXECUTION_COMPLETED

    @property
    def failed_event(
        self,
    ) -> EventType:

        return EventType.EXECUTION_FAILED

    @property
    def cancelled_event(
        self,
    ) -> EventType:

        return EventType.EXECUTION_CANCELLED
