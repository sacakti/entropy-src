from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums import EventType

from .dispatcher import EventDispatcher
from .event import PluginResultEvent
from .lifecycle import LifecycleEmitter
from .log import LogEmitter
from .message import MessageEmitter

if TYPE_CHECKING:
    from core.runtime.execution import WorkflowExecution
    from core.runtime.node import RuntimeNode


class Emitter:
    """
    Facade exposing all observability emitters.
    """

    def __init__(
        self,
        dispatcher: EventDispatcher,
        source: str,
    ) -> None:

        self._dispatcher = dispatcher
        self._source = source

        self._lifecycle = LifecycleEmitter(
            dispatcher,
            source,
        )

        self.log = LogEmitter(
            dispatcher,
            source,
        )

        self.message = MessageEmitter(
            dispatcher,
            source,
        )

    def lifecycle(
        self,
        event_type: EventType,
        execution: WorkflowExecution,
        node: RuntimeNode,
    ) -> None:

        self._lifecycle.emit(
            event_type,
            execution,
            node,
        )

    def result(
        self,
        execution: WorkflowExecution,
        node: RuntimeNode,
        result: dict,
    ) -> None:

        self._dispatcher.dispatch(
            PluginResultEvent(
                source=self._source,
                execution=execution,
                node=node,
                result=result,
            )
        )
