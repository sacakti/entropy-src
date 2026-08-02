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
    Creates and caches execution loggers.
    """

    FORMAT = (
        "%(asctime)s | "
        "%(levelname)-8s | "
        "%(name)s | "
        "%(message)s"
    )

    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        directory: Path,
        level: str = "INFO",
    ) -> None:

        self._directory = directory

        self._level = getattr(
            logging,
            level.upper(),
            logging.INFO,
        )

        self._cache: dict[str, ExecutionLogger] = {}

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def logger(
        self,
        name: str,
    ) -> ExecutionLogger:
        """
        Return a named logger.
        """

        logger = self._cache.get(
            name,
        )

        if logger is not None:

            return logger

        logger = self._create(
            name,
        )

        self._cache[name] = logger

        return logger

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create(
        self,
        name: str,
    ) -> ExecutionLogger:
        """
        Create a new logger.
        """

        instance = logging.getLogger(
            f"entropy.{name}",
        )

        instance.handlers.clear()

        instance.setLevel(
            self._level,
        )

        instance.propagate = False

        handler = create_handler(
            self._directory / f"{name}.log",
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """
        Clear cached loggers.
        """

        self._cache.clear()
