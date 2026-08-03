"""
Execution logger.
"""

from __future__ import annotations

import logging

from core.models.logger import LogLevel


class ExecutionLogger:
    """
    Thin wrapper around ``logging.Logger``.
    """

    _LEVELS = {
        LogLevel.DEBUG: logging.DEBUG,
        LogLevel.INFO: logging.INFO,
        LogLevel.SUCCESS: logging.INFO,
        LogLevel.WARNING: logging.WARNING,
        LogLevel.ERROR: logging.ERROR,
        LogLevel.CRITICAL: logging.CRITICAL,
    }

    def __init__(
        self,
        logger: logging.Logger,
    ) -> None:

        self._logger = logger

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(
        self,
        level: LogLevel,
        module: str,
        message: str,
    ) -> None:
        """
        Write a log entry.
        """

        self._logger.log(
            self._LEVELS[level],
            message,
            extra={
                "module_name": module,
            },
        )

    # ------------------------------------------------------------------
    # Advanced
    # ------------------------------------------------------------------

    @property
    def logger(self) -> logging.Logger:

        return self._logger
