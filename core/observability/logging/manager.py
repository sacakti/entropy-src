"""
Logging manager.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .logger import ExecutionLogger
from .rotation import create_handler


class LoggingManager:
    """
    Factory for execution loggers.

    Creates and caches loggers by their target log file.
    """

    FORMAT = "%(asctime)s " "%(levelname)-8s " "<module:%(module_name)s> " "%(message)s"

    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        level: str = "INFO",
    ) -> None:

        self._level = getattr(
            logging,
            level.upper(),
            logging.INFO,
        )

        self._loggers: dict[
            Path,
            ExecutionLogger,
        ] = {}

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def logger(
        self,
        file: Path,
    ) -> ExecutionLogger:
        """
        Return a logger for the given log file.
        """

        logger = self._loggers.get(
            file,
        )

        if logger is not None:

            return logger

        logger = self._create(
            file,
        )

        self._loggers[file] = logger

        return logger

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create(
        self,
        file: Path,
    ) -> ExecutionLogger:
        """
        Create a logger for a log file.
        """

        instance = logging.getLogger(
            str(file),
        )

        instance.handlers.clear()

        instance.setLevel(
            self._level,
        )

        instance.propagate = False

        handler = create_handler(
            file,
        )

        handler.setFormatter(
            logging.Formatter(
                self.FORMAT,
                self.DATEFMT,
            )
        )

        instance.addHandler(
            handler,
        )

        return ExecutionLogger(
            instance,
        )
