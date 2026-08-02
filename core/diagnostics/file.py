"""
File diagnostics sink.
"""

from __future__ import annotations

from pathlib import Path

from .entry import LogEntry
from .sink import Sink


class FileSink(Sink):
    """
    Writes diagnostic entries to a log file.
    """

    def __init__(
        self,
        file: Path,
    ) -> None:

        self._file = file

        self._file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ------------------------------------------------------------------
    # Sink
    # ------------------------------------------------------------------

    def write(
        self,
        entry: LogEntry,
    ) -> None:

        with self._file.open(
            "a",
            encoding="utf-8",
        ) as handle:

            handle.write(
                "{} [{:<7}] [{}] {}\n".format(
                    entry.timestamp.strftime(
                        "%Y-%m-%d %H:%M:%S",
                    ),
                    entry.level.name,
                    entry.source,
                    entry.message,
                )
            )
