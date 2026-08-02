"""
Diagnostic dispatcher.
"""

from __future__ import annotations

from .entry import LogEntry
from .sink import Sink


class Dispatcher:
    """
    Dispatch diagnostic entries to sinks.
    """

    def __init__(self) -> None:

        self._sinks: list[Sink] = []

    def register(
        self,
        sink: Sink,
    ) -> None:

        self._sinks.append(
            sink,
        )

    def unregister(
        self,
        sink: Sink,
    ) -> None:

        self._sinks.remove(
            sink,
        )

    def dispatch(
        self,
        entry: LogEntry,
    ) -> None:

        for sink in self._sinks:

            sink.write(
                entry,
            )
