"""
Entropy Output Manager.

Single public interface for:
    - Console output
    - Logging
"""

from __future__ import annotations

from pathlib import Path

from core.constants import CATEGORIES

from .banner import Banner
from .category import CategoryLogger
from .console import ConsoleEngine
from .logger import LoggerEngine


class OutputManager:

    def __init__(self):

        self._console = ConsoleEngine()

        self._logger = LoggerEngine()

        #
        # Create category loggers
        #
        for category in CATEGORIES:

            setattr(
                self,
                category,
                CategoryLogger(
                    self,
                    category,
                ),
            )

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    def initialize(
        self,
        log_directory: Path,
        level: str = "INFO",
        console_level: str = "NORMAL",
    ):

        self._logger.initialize(
            log_directory=log_directory,
            level=level,
        )

        self._console.initialize(
            console_level,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def emit(
        self,
        level: str,
        category: str,
        message: str,
        exception: bool = False,
        **kwargs,
    ):

        level = level.upper()

        #
        # Always log
        #

        self._logger.write(
            level=level,
            category=category,
            message=message,
            exception=exception,
        )

        #
        # Console filtering
        #

        if not self._console.should_emit(level):
            return

        task = kwargs.get("task")

        if level == "INFO":
            self._console.info(message)

        elif level == "DEBUG":
            self._console.debug(message)

        elif level == "SUCCESS":
            self._console.success(
                message,
                task,
            )

        elif level == "WARNING":
            self._console.warning(
                message,
                task,
            )

        elif level == "ERROR":
            self._console.error(
                message,
                task,
            )

    # ------------------------------------------------------------------
    # Banner
    # ------------------------------------------------------------------

    def banner(
        self,
        app_name: str,
        version: str,
    ):

        self._console.banner(
            Banner.build(
                app_name,
                version,
            )
        )

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def progress(
        self,
        message: str,
    ):

        return self._console.progress(message)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def step(
        self,
        step_no: int,
        title: str,
    ):

        self._console.step(
            step_no,
            title,
        )

    def sub(
        self,
        message: str,
    ):

        self._console.sub(message)

    # ------------------------------------------------------------------
    # Generic
    # ------------------------------------------------------------------

    def print(
        self,
        *args,
        **kwargs,
    ):

        self._console.print(
            *args,
            **kwargs,
        )

    def rule(
        self,
        title: str = "",
    ):

        self._console.rule(title)

    def table(
        self,
        title,
        columns,
        rows,
    ):

        self._console.table(
            title,
            columns,
            rows,
        )

    def panel(
        self,
        title,
        lines,
    ):
        self._console.panel(title, lines)

    def prompt(self, message: str, default: None = None, password: bool = False):
        return self._console.prompt(message=message, default=default, password=password)

    def confirm(
        self,
        message: str,
        default: bool = False,
    ) -> bool:

        return self._console.confirm(message=message, default=default)

    def shutdown(self):

        self._console.shutdown()

        self._logger.shutdown()


output = OutputManager()
