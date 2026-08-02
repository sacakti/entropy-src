"""
Runtime event dispatcher.
"""

from __future__ import annotations

from .event import Event
from .sink import Sink


class EventDispatcher:
    """
    Dispatches runtime events to registered sinks.
    """

    def __init__(self) -> None:

        self._sinks: list[Sink] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        sink: Sink,
    ) -> None:
        """
        Register an event sink.
        """

        self._sinks.append(sink)

    def unregister(
        self,
        sink: Sink,
    ) -> None:
        """
        Remove an event sink.
        """

        if sink in self._sinks:

            self._sinks.remove(sink)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(
        self,
        event: Event,
    ) -> None:
        """
        Dispatch an event to all registered sinks.
        """

        for sink in self._sinks:

            sink.publish(event)
