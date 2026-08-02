"""
Runtime event emitter.
"""

from __future__ import annotations

from core.models.logger import LogLevel
from core.runtime.node import RuntimeNode

from ..models.enums import EventType
from .dispatcher import EventDispatcher
from .event import Event, LogEvent


class Emitter:
    """
    Emits runtime observation events.

    An emitter is bound to a specific event source
    (workflow, shell, git, sqlplus, etc.).
    """

    def __init__(
        self,
        dispatcher: EventDispatcher,
        source: str,
    ) -> None:

        self._dispatcher = dispatcher

        self._source = source

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def emit(
        self,
        event_type: EventType,
        execution_id: str,
        node: RuntimeNode,
    ) -> None:
        """
        Emit a runtime observation event.
        """

        event = Event(
            type=event_type,
            source=self._source,
            execution_id=execution_id,
            node=node,
        )

        self._dispatcher.dispatch(
            event,
        )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(
        self,
        level: LogLevel,
        message: str,
    ) -> None:
        """
        Emit a log event.
        """

        self._dispatcher.dispatch(
            LogEvent(
                source=self._source,
                level=level,
                message=message,
            )
        )

    def debug(
        self,
        message: str,
    ) -> None:

        self.log(
            LogLevel.DEBUG,
            message,
        )


    def info(
        self,
        message: str,
    ) -> None:

        self.log(
            LogLevel.INFO,
            message,
        )


    def warning(
        self,
        message: str,
    ) -> None:

        self.log(
            LogLevel.WARNING,
            message,
        )


    def error(
        self,
        message: str,
    ) -> None:

        self.log(
            LogLevel.ERROR,
            message,
        )


    def critical(
        self,
        message: str,
    ) -> None:

        self.log(
            LogLevel.CRITICAL,
            message,
        )
