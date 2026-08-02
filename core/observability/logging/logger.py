"""
Execution logger.
"""

from __future__ import annotations

import logging


class ExecutionLogger:
    """
    Thin wrapper around ``logging.Logger``.

    Provides a minimal, stable interface for the
    logging subsystem.
    """

    def __init__(
        self,
        logger: logging.Logger,
    ) -> None:

        self._logger = logger

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def debug(
        self,
        message: str,
    ) -> None:

        self._logger.debug(message)

    def info(
        self,
        message: str,
    ) -> None:

        self._logger.info(message)

    def warning(
        self,
        message: str,
    ) -> None:

        self._logger.warning(message)

    def error(
        self,
        message: str,
    ) -> None:

        self._logger.error(message)

    def exception(
        self,
        message: str,
    ) -> None:

        self._logger.exception(message)

    # ------------------------------------------------------------------
    # Advanced
    # ------------------------------------------------------------------

    @property
    def logger(self) -> logging.Logger:
        """
        Return the underlying Python logger.

        Prefer using the wrapper methods whenever possible.
        """

        return self._logger
