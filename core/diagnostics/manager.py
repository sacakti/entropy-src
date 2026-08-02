"""
Diagnostics manager.
"""

from __future__ import annotations

from .dispatcher import Dispatcher
from .logger import Logger
from .sink import Sink


class DiagnosticsManager:
    """
    Diagnostics subsystem.
    """

    def __init__(self) -> None:

        self._dispatcher = Dispatcher()

        self._loggers: dict[str, Logger] = {}

    # ------------------------------------------------------------------
    # Loggers
    # ------------------------------------------------------------------

    def logger(
        self,
        source: str,
    ) -> Logger:

        logger = self._loggers.get(
            source,
        )

        if logger is None:

            logger = Logger(
                dispatcher=self._dispatcher,
                source=source,
            )

            self._loggers[source] = logger

        return logger

    # ------------------------------------------------------------------
    # Sinks
    # ------------------------------------------------------------------

    def register(
        self,
        sink: Sink,
    ) -> None:

        self._dispatcher.register(
            sink,
        )

    def unregister(
        self,
        sink: Sink,
    ) -> None:

        self._dispatcher.unregister(
            sink,
        )
