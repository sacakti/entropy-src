"""
Runtime event emitter.
"""

from __future__ import annotations

from core.runtime.node import RuntimeNode

from ..models.enums import EventType
from .dispatcher import EventDispatcher
from .event import Event


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

    # # ------------------------------------------------------------------
    # # Logging
    # # ------------------------------------------------------------------

    # def debug(
    #     self,
    #     message: str,
    # ) -> None:

    #     self._log(
    #         LogLevel.DEBUG,
    #         message,
    #     )

    # def info(
    #     self,
    #     message: str,
    # ) -> None:

    #     self._log(
    #         LogLevel.INFO,
    #         message,
    #     )

    # def success(
    #     self,
    #     message: str,
    # ) -> None:

    #     self._log(
    #         LogLevel.SUCCESS,
    #         message,
    #     )

    # def warning(
    #     self,
    #     message: str,
    # ) -> None:

    #     self._log(
    #         LogLevel.WARNING,
    #         message,
    #     )

    # def error(
    #     self,
    #     message: str,
    # ) -> None:

    #     self._log(
    #         LogLevel.ERROR,
    #         message,
    #     )

    # def _log(
    #     self,
    #     level: LogLevel,
    #     message: str,
    # ) -> None:

    #     event = Event.log(
    #         source=self._source,
    #         level=level,
    #         message=message,
    #     )

    #     self._dispatcher.dispatch(
    #         event,
    #     )
