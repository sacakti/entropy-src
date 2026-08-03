"""
No-op observability emitter.
"""

from __future__ import annotations

from core.models.enums import EventType
from core.models.logger import LogLevel


class NullEmitter:
    """
    No-op emitter used when observability is unavailable.
    """

    def emit(
        self,
        event_type: EventType,
        execution_id,
        node,
    ) -> None:
        pass

    def log(
        self,
        level: LogLevel,
        message: str,
    ) -> None:
        pass

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def success(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def critical(self, message: str) -> None:
        pass
