"""
Runtime lifecycle emitter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums import EventType

from .dispatcher import EventDispatcher
from .event import LifecycleEvent

if TYPE_CHECKING:
    from core.runtime.execution import WorkflowExecution
    from core.runtime.node import RuntimeNode


class LifecycleEmitter:
    """
    Emits runtime lifecycle events.
    """

    def __init__(
        self,
        dispatcher: EventDispatcher,
        source: str,
    ) -> None:

        self._dispatcher = dispatcher
        self._source = source

    def emit(
        self,
        event_type: EventType,
        execution: WorkflowExecution,
        node: RuntimeNode,
    ) -> None:

        self._dispatcher.dispatch(
            LifecycleEvent(
                type=event_type,
                source=self._source,
                execution=execution,
                node=node,
            )
        )
