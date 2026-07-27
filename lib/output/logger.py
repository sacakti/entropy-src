"""
Entropy logging engine.
"""

from __future__ import annotations

import logging

from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.constants import CATEGORIES


class LoggerEngine:

    def __init__(self):

        self._loggers = {}

        self._initialized = False

    def initialize(
        self,
        log_directory: Path,
        level: str = "INFO",
        max_bytes: int = 20 * 1024 * 1024,
        backup_count: int = 10,
    ):

        if self._initialized:
            return

        log_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-10s | %(message)s"
        )

        log_level = getattr(
            logging,
            level.upper(),
            logging.INFO,
        )

        for name in CATEGORIES:

            logger = logging.getLogger(name)

            logger.setLevel(log_level)

            logger.propagate = False

            #
            # Avoid duplicate handlers
            #
            logger.handlers.clear()

            handler = RotatingFileHandler(
                log_directory / f"{name}.log",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )

            handler.setFormatter(formatter)

            logger.addHandler(handler)

            self._loggers[name] = logger

        self._initialized = True

    def write(
        self,
        level: str,
        category: str,
        message: str,
        exception: bool = False,
    ):

        logger = self._loggers.get(category)

        if logger is None:
            return

        if exception:
            logger.exception(message)
            return

        level = level.upper()

        if level == "DEBUG":
            logger.debug(message)

        elif level == "INFO":
            logger.info(message)

        elif level == "SUCCESS":
            logger.info(message)

        elif level == "WARNING":
            logger.warning(message)

        elif level == "ERROR":
            logger.error(message)

        else:
            logger.info(message)

    def shutdown(self):

        for logger in self._loggers.values():

            handlers = logger.handlers[:]

            for handler in handlers:

                handler.close()

                logger.removeHandler(handler)

        self._loggers.clear()

        self._initialized = False