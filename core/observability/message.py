"""
Runtime message emitter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.logger import LogLevel

from .dispatcher import EventDispatcher
from .event import MessageEvent

if TYPE_CHECKING:
    from core.runtime.execution import WorkflowExecution
    from core.runtime.node import RuntimeNode


class MessageEmitter:
    """
    Emits runtime user messages.
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
        level: LogLevel,
        execution: WorkflowExecution,
        node: RuntimeNode,
        message: str,
    ) -> None:

        self._dispatcher.dispatch(
            MessageEvent(
                source=self._source,
                execution=execution,
                node=node,
                level=level,
                message=message,
            )
        )

    def debug(
        self,
        execution: WorkflowExecution,
        node: RuntimeNode,
        message: str,
    ) -> None:

        self.emit(LogLevel.DEBUG, execution, node, message)

    def info(
        self,
        execution: WorkflowExecution,
        node: RuntimeNode,
        message: str,
    ) -> None:

        self.emit(LogLevel.INFO, execution, node, message)

    def success(
        self,
        execution: WorkflowExecution,
        node: RuntimeNode,
        message: str,
    ) -> None:

        self.emit(LogLevel.SUCCESS, execution, node, message)

    def warning(
        self,
        execution: WorkflowExecution,
        node: RuntimeNode,
        message: str,
    ) -> None:

        self.emit(LogLevel.WARNING, execution, node, message)

    def error(
        self,
        execution: WorkflowExecution,
        node: RuntimeNode,
        message: str,
    ) -> None:

        self.emit(LogLevel.ERROR, execution, node, message)
