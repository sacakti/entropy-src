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
    Creates the application logger.
    """

    FORMAT = (
        "%(asctime)s "
        "%(levelname)-8s "
        "<module:%(module_name)s> "
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

        self._logger = self._create()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def logger(
        self,
        source: str = "entropy",
    ) -> ExecutionLogger:
        """
        Return a logger.

        Parameters
        ----------
        source:
            Logger name.
        """

        #
        # For now we only maintain a single logger.
        #
        # Later this will return per-workflow/per-plugin
        # loggers.
        #

        return self._logger

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create(
        self,
    ) -> ExecutionLogger:
        """
        Create the application logger.
        """

        instance = logging.getLogger(
            "entropy",
        )

        instance.handlers.clear()

        instance.setLevel(
            self._level,
        )

        instance.propagate = False

        handler = create_handler(
            self._directory / "entropy.log",
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
