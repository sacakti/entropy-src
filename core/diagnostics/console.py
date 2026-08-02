"""
Console diagnostics sink.
"""

from __future__ import annotations

from rich.console import Console

from core.models.logger import LogLevel

from .entry import LogEntry
from .sink import Sink


class ConsoleSink(Sink):
    """
    Writes diagnostic entries to the console.
    """

    _STYLES = {
        LogLevel.DEBUG: "dim",
        LogLevel.INFO: "cyan",
        LogLevel.SUCCESS: "green",
        LogLevel.WARNING: "yellow",
        LogLevel.ERROR: "red",
    }

    def __init__(self) -> None:

        self._console = Console()

    # ------------------------------------------------------------------
    # Sink
    # ------------------------------------------------------------------

    def write(
        self,
        entry: LogEntry,
    ) -> None:

        style = self._STYLES.get(
            entry.level,
            "white",
        )

        self._console.print(f"[{style}][{entry.level.name:<7}][/{style}] {entry.message}")
