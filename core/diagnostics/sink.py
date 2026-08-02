"""
Diagnostic sink.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .entry import LogEntry


class Sink(ABC):
    """
    Base diagnostics sink.
    """

    @abstractmethod
    def write(
        self,
        entry: LogEntry,
    ) -> None:
        """
        Write a diagnostic entry.
        """
