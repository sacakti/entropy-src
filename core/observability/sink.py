"""
Observability sink.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .event import BaseEvent


class Sink(ABC):
    """
    Base class for all observability sinks.

    A sink consumes runtime events and publishes them
    to a specific destination.
    """

    @abstractmethod
    def publish(
        self,
        event: BaseEvent,
    ) -> None:
        """
        Publish a runtime event.
        """
        ...
