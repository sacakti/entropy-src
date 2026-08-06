"""
Application log emitter.
"""

from __future__ import annotations

from core.models.logger import LogLevel

from .dispatcher import EventDispatcher
from .event import LogEvent


class LogEmitter:
    """
    Emits application log events.
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
        message: str,
    ) -> None:

        self._dispatcher.dispatch(
            LogEvent(
                source=self._source,
                level=level,
                message=message,
            )
        )

    def debug(self, message: str) -> None:
        self.emit(LogLevel.DEBUG, message)

    def info(self, message: str) -> None:
        self.emit(LogLevel.INFO, message)

    def warning(self, message: str) -> None:
        self.emit(LogLevel.WARNING, message)

    def error(self, message: str) -> None:
        self.emit(LogLevel.ERROR, message)

    def critical(self, message: str) -> None:
        self.emit(LogLevel.CRITICAL, message)
