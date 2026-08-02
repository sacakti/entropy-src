"""
Diagnostics logger.
"""

from __future__ import annotations

from core.models.logger import LogLevel

from .dispatcher import Dispatcher
from .entry import LogEntry


class Logger:
    """
    Diagnostic logger.
    """

    def __init__(
        self,
        dispatcher: Dispatcher,
        source: str,
    ) -> None:

        self._dispatcher = dispatcher
        self._source = source

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------

    def debug(
        self,
        message: str,
    ) -> None:

        self._write(
            LogLevel.DEBUG,
            message,
        )

    def info(
        self,
        message: str,
    ) -> None:

        self._write(
            LogLevel.INFO,
            message,
        )

    def success(
        self,
        message: str,
    ) -> None:

        self._write(
            LogLevel.SUCCESS,
            message,
        )

    def warning(
        self,
        message: str,
    ) -> None:

        self._write(
            LogLevel.WARNING,
            message,
        )

    def error(
        self,
        message: str,
    ) -> None:

        self._write(
            LogLevel.ERROR,
            message,
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _write(
        self,
        level: LogLevel,
        message: str,
    ) -> None:

        self._dispatcher.dispatch(
            LogEntry(
                level=level,
                source=self._source,
                message=message,
            )
        )
