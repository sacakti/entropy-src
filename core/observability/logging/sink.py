"""
Logging sink.
"""

from __future__ import annotations

from ...models.enums import EventType
from ..event import BaseEvent, Event
from ..sink import Sink
from .logger import ExecutionLogger
from .manager import LoggingManager


class LoggingSink(Sink):
    """
    Logging observability sink.

    Persists runtime events to log files.
    """

    def __init__(
        self,
        manager: LoggingManager,
    ) -> None:

        self._manager = manager

    # ------------------------------------------------------------------
    # Sink
    # ------------------------------------------------------------------

    def publish(
        self,
        event: BaseEvent,
    ) -> None:

        if not isinstance(event, Event):
            return

        logger = self._logger(event)

        message = self._message(event)

        self._write(
            logger,
            event,
            message,
        )

    # ------------------------------------------------------------------
    # Logger
    # ------------------------------------------------------------------

    def _logger(
        self,
        event: Event,
    ) -> ExecutionLogger:
        """
        Resolve logger for the event source.
        """

        return self._manager.logger(
            event.source,
        )

    # ------------------------------------------------------------------
    # Message
    # ------------------------------------------------------------------

    @staticmethod
    def _message(
        event: Event,
    ) -> str:
        """
        Format a runtime event message.
        """

        action = {
            EventType.EXECUTION_STARTED: "Execution started",
            EventType.EXECUTION_COMPLETED: "Execution completed",
            EventType.EXECUTION_FAILED: "Execution failed",
            EventType.EXECUTION_CANCELLED: "Execution cancelled",
            EventType.STEP_STARTED: "Step started",
            EventType.STEP_COMPLETED: "Step completed",
            EventType.STEP_FAILED: "Step failed",
            EventType.STEP_SKIPPED: "Step skipped",
            EventType.STAGE_STARTED: "Stage started",
            EventType.STAGE_COMPLETED: "Stage completed",
            EventType.STAGE_FAILED: "Stage failed",
            EventType.ACTIVITY_STARTED: "Activity started",
            EventType.ACTIVITY_COMPLETED: "Activity completed",
            EventType.ACTIVITY_FAILED: "Activity failed",
        }[event.type]

        duration = ""

        if event.node.duration_ms is not None:

            duration = f" ({event.node.duration_ms} ms)"

        return f"{action}: {event.name}{duration}"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    def _write(
        logger: ExecutionLogger,
        event: Event,
        message: str,
    ) -> None:
        """
        Write the event using the appropriate log level.
        """

        module = event.source

        if event.type in (
            EventType.EXECUTION_FAILED,
            EventType.STEP_FAILED,
            EventType.STAGE_FAILED,
            EventType.ACTIVITY_FAILED,
        ):

            logger.error(
                module,
                message,
            )

            return

        logger.info(
            module,
            message,
        )
