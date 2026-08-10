"""
Plugin runtime message API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.logger import LogLevel

if TYPE_CHECKING:
    from core.observability.emitter import Emitter
    from core.runtime.context import ExecutionContext


class PluginMessage:
    """
    Runtime message API exposed to plugins.
    """

    def __init__(
        self,
        runtime: ExecutionContext,
        emitter: Emitter,
    ) -> None:

        self._runtime = runtime
        self._emitter = emitter.message

    def emit(
        self,
        level: LogLevel,
        message: str,
    ) -> None:

        node = self._runtime.node

        assert node is not None

        self._emitter.emit(
            level=level,
            execution=self._runtime.execution,
            node=node,
            message=message,
        )

    def debug(
        self,
        message: str,
    ) -> None:

        self.emit(
            LogLevel.DEBUG,
            message,
        )

    def info(
        self,
        message: str,
    ) -> None:

        self.emit(
            LogLevel.INFO,
            message,
        )

    def success(
        self,
        message: str,
    ) -> None:

        self.emit(
            LogLevel.SUCCESS,
            message,
        )

    def warning(
        self,
        message: str,
    ) -> None:

        self.emit(
            LogLevel.WARNING,
            message,
        )

    def error(
        self,
        message: str,
    ) -> None:

        self.emit(
            LogLevel.ERROR,
            message,
        )
