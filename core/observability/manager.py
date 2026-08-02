"""
Observability manager.
"""

from __future__ import annotations

from .dispatcher import EventDispatcher
from .emitter import Emitter
from .sink import Sink


class ObservabilityManager:
    """
    Central observability subsystem.

    Owns the dispatcher, sinks and emitters.
    """

    def __init__(self) -> None:

        self._dispatcher = EventDispatcher()

        self._emitters: dict[str, Emitter] = {}

    # ------------------------------------------------------------------
    # Emitters
    # ------------------------------------------------------------------

    def emitter(
        self,
        source: str,
    ) -> Emitter:
        """
        Return an emitter bound to the given source.
        """

        emitter = self._emitters.get(
            source,
        )

        if emitter is None:

            emitter = Emitter(
                dispatcher=self._dispatcher,
                source=source,
            )

            self._emitters[source] = emitter

        return emitter

    # ------------------------------------------------------------------
    # Sinks
    # ------------------------------------------------------------------

    def register(
        self,
        sink: Sink,
    ) -> None:
        """
        Register an observability sink.
        """

        self._dispatcher.register(
            sink,
        )

    def unregister(
        self,
        sink: Sink,
    ) -> None:
        """
        Remove an observability sink.
        """

        self._dispatcher.unregister(
            sink,
        )
