"""
Logging sink.
"""

from __future__ import annotations

import json

from ...models.enums import EventType
from ..event import (
    BaseEvent,
    LifecycleEvent,
    LogEvent,
    MessageEvent,
    PluginResultEvent,
)
from ..sink import Sink
from .logger import ExecutionLogger
from .manager import LoggingManager


class LoggingSink(Sink):
    """
    Logging observability sink.

    Persists runtime events to workflow log files.
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

        if isinstance(
            event,
            LifecycleEvent,
        ):

            logger = self._logger(
                event,
            )

            self._write_lifecycle(
                logger,
                event,
            )

            return

        if isinstance(
            event,
            MessageEvent,
        ):

            logger = self._logger(
                event,
            )

            self._write_message(
                logger,
                event,
            )

            return

        if isinstance(
            event,
            PluginResultEvent,
        ):

            logger = self._logger(
                event,
            )

            self._write_result(
                logger,
                event,
            )

            return

        if isinstance(
            event,
            LogEvent,
        ):

            #
            # Application logging is handled by LoggingManager.
            #

            return

    # ------------------------------------------------------------------
    # Logger
    # ------------------------------------------------------------------

    def _logger(
        self,
        event: LifecycleEvent,
    ) -> ExecutionLogger:
        """
        Resolve the workflow execution logger.
        """

        return self._manager.logger(
            event.workspace / "workflow.log",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _write_lifecycle(
        logger: ExecutionLogger,
        event: LifecycleEvent,
    ) -> None:
        """
        Persist a lifecycle event.
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

        message = action

        if event.name:

            message += f": {event.name}"

        if event.node.duration_ms is not None:

            message += f" ({event.node.duration_ms} ms)"

        if event.type in (
            EventType.EXECUTION_FAILED,
            EventType.STEP_FAILED,
            EventType.STAGE_FAILED,
            EventType.ACTIVITY_FAILED,
        ):

            logger.error(
                event.source,
                message,
            )

        else:

            logger.info(
                event.source,
                message,
            )

    # ------------------------------------------------------------------
    # Runtime Messages
    # ------------------------------------------------------------------

    @staticmethod
    def _write_message(
        logger: ExecutionLogger,
        event: MessageEvent,
    ) -> None:
        """
        Persist a runtime message.
        """

        if event.level.name == "DEBUG":

            logger.debug(
                event.source,
                event.message,
            )

        elif event.level.name == "WARNING":

            logger.warning(
                event.source,
                event.message,
            )

        elif event.level.name == "ERROR":

            logger.error(
                event.source,
                event.message,
            )

        elif event.level.name == "CRITICAL":

            logger.critical(
                event.source,
                event.message,
            )

        else:

            logger.info(
                event.source,
                event.message,
            )

    @staticmethod
    def _write_result(
        logger: ExecutionLogger,
        event: PluginResultEvent,
    ) -> None:

        logger.info(
            "plugin",
            f"Plugin result: {event.node.name}\n" f"{json.dumps(event.result, indent=2)}",
        )
