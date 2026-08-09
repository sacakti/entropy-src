"""
Workflow event persistence sink.
"""

from __future__ import annotations

from core.observability.event import (
    BaseEvent,
    LifecycleEvent,
    MessageEvent,
)
from core.observability.sink import Sink

from .manager import WorkflowJobManager


class WorkflowEventSink(Sink):
    """
    Persists workflow runtime events.

    Only workflow lifecycle and runtime message events are
    persisted. Application log events are intentionally ignored.
    """

    def __init__(
        self,
        jobs: WorkflowJobManager,
    ) -> None:

        self._jobs = jobs

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(
        self,
        event: BaseEvent,
    ) -> None:

        if isinstance(
            event,
            LifecycleEvent,
        ):

            self._lifecycle(
                event,
            )

            return

        if isinstance(
            event,
            MessageEvent,
        ):

            self._message(
                event,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _lifecycle(
        self,
        event: LifecycleEvent,
    ) -> None:

        job_id = event.execution.get(
            "job_id",
        )

        if job_id is None:

            return

        self._jobs.event(
            job_id=job_id,
            execution_id=event.execution_id,
            event_type=event.type.value,
            source=event.source,
            node_type=event.node.type.value,
            node_id=event.node.id,
            node_name=event.node.name,
            payload={
                "status": event.node.status.value,
                "duration_ms": event.node.duration_ms,
                "metadata": dict(
                    event.node.metadata,
                ),
            },
        )

    # ------------------------------------------------------------------
    # Message
    # ------------------------------------------------------------------

    def _message(
        self,
        event: MessageEvent,
    ) -> None:

        job_id = event.execution.get(
            "job_id",
        )

        if job_id is None:

            return

        self._jobs.event(
            job_id=job_id,
            execution_id=event.execution_id,
            event_type="message",
            source=event.source,
            level=event.level.value,
            message=event.message,
            node_type=event.node.type.value,
            node_id=event.node.id,
            node_name=event.node.name,
        )
