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
    # Generic
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
    # Convenience
    # ------------------------------------------------------------------

    def debug(
        self,
        module: str,
        message: str,
    ) -> None:

        self.log(
            LogLevel.DEBUG,
            module,
            message,
        )

    def info(
        self,
        module: str,
        message: str,
    ) -> None:

        self.log(
            LogLevel.INFO,
            module,
            message,
        )

    def warning(
        self,
        module: str,
        message: str,
    ) -> None:

        self.log(
            LogLevel.WARNING,
            module,
            message,
        )

    def error(
        self,
        module: str,
        message: str,
    ) -> None:

        self.log(
            LogLevel.ERROR,
            module,
            message,
        )

    def critical(
        self,
        module: str,
        message: str,
    ) -> None:

        self.log(
            LogLevel.CRITICAL,
            module,
            message,
        )

    # ------------------------------------------------------------------
    # Advanced
    # ------------------------------------------------------------------

    @property
    def logger(
        self,
    ) -> logging.Logger:

        return self._logger
