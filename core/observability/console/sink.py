"""
Rich console sink.
"""

from __future__ import annotations

from core.models.logger import LogLevel

from ..event import (
    BaseEvent,
    LifecycleEvent,
    LogEvent,
    MessageEvent,
)
from ..sink import Sink
from .renderer import ConsoleRenderer


class ConsoleSink(Sink):
    """
    Console observability sink.

    Converts runtime events into terminal rendering.
    """

    def __init__(
        self,
        renderer: ConsoleRenderer,
    ) -> None:

        self._renderer = renderer

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

            handler = getattr(
                self,
                f"_{event.type.name.lower()}",
                None,
            )

            if handler is not None:
                handler(event)

            return

        if isinstance(
            event,
            MessageEvent,
        ):

            self._message_event(
                event,
            )

            return

        if isinstance(
            event,
            LogEvent,
        ):

            #
            # Console intentionally ignores application logs.
            # They belong in the log file.
            #

            return

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _indent(
        self,
        event: LifecycleEvent,
    ) -> str:
        """
        Indentation used for activity output.

        Workflow = 0
        Step     = 1
        Stage    = 2 (hidden)
        Activity = 3
        """

        return "  " * max(
            0,
            event.node.depth - 1,
        )

    def _message(
        self,
        event: LifecycleEvent,
    ) -> str:

        return f"{self._indent(event)}{event.name}"

    # ------------------------------------------------------------------
    # Runtime Messages
    # ------------------------------------------------------------------

    def _message_event(
        self,
        event: MessageEvent,
    ) -> None:

        indent = "  " * max(
            0,
            event.node.depth - 1,
        )

        message = (
            indent
            + event.message.replace(
                "\n",
                "\n" + indent,
            )
        )

        if event.level is LogLevel.INFO:

            self._renderer.info(message)

        elif event.level is LogLevel.SUCCESS:

            self._renderer.success(message)

        elif event.level is LogLevel.WARNING:

            self._renderer.warning(message)

        elif event.level is LogLevel.ERROR:

            self._renderer.error(message)

        elif event.level is LogLevel.DEBUG:

            self._renderer.debug(message)

        else:

            self._renderer.print(message)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execution_started(
        self,
        event: LifecycleEvent,
    ) -> None:

        self._renderer.info(
            f"Execution started : {event.name}",
        )

    def _execution_completed(
        self,
        event: LifecycleEvent,
    ) -> None:

        duration = event.node.duration_ms or 0

        self._renderer.success(
            f"Execution completed : {event.name} ({duration} ms)",
        )

    def _execution_failed(
        self,
        event: LifecycleEvent,
    ) -> None:

        duration = event.node.duration_ms or 0

        self._renderer.error(
            f"Execution failed : {event.name} ({duration} ms)",
        )

    def _execution_cancelled(
        self,
        event: LifecycleEvent,
    ) -> None:

        duration = event.node.duration_ms or 0

        self._renderer.warning(
            f"Execution cancelled : {event.name} ({duration} ms)",
        )

    # ------------------------------------------------------------------
    # Step
    # ------------------------------------------------------------------

    def _step_started(
        self,
        event: LifecycleEvent,
    ) -> None:

        self._renderer.blank()
        self._renderer.rule()

        index = event.node.get("index", "?")
        total = event.node.get("total", "?")

        self._renderer.heading(
            f"Step {index}/{total} : {event.name}",
        )

    def _step_completed(
        self,
        event: LifecycleEvent,
    ) -> None:

        duration = event.node.duration_ms or 0

        self._renderer.success(
            f"Step {event.node.get('index')}/{event.node.get('total')} : "
            f"{event.name} ({duration} ms)"
        )

        self._end_step(
            event,
        )

    def _step_failed(
        self,
        event: LifecycleEvent,
    ) -> None:

        duration = event.node.duration_ms or 0

        self._renderer.error(
            f"Step {event.node.get('index')}/{event.node.get('total')} : "
            f"{event.name} ({duration} ms)"
        )

        self._end_step(
            event,
        )

    def _step_skipped(
        self,
        event: LifecycleEvent,
    ) -> None:

        self._renderer.warning(
            f"Step {event.node.get('index')}/{event.node.get('total')} : "
            f"{event.name}"
        )

        self._end_step(
            event,
        )

    # ------------------------------------------------------------------
    # Stage
    # ------------------------------------------------------------------

    def _stage_started(
        self,
        event: LifecycleEvent,
    ) -> None:
        return

    def _stage_completed(
        self,
        event: LifecycleEvent,
    ) -> None:
        return

    def _stage_failed(
        self,
        event: LifecycleEvent,
    ) -> None:
        return

    # ------------------------------------------------------------------
    # Activity
    # ------------------------------------------------------------------

    def _activity_started(
        self,
        event: LifecycleEvent,
    ) -> None:

        self._renderer.spinner(
            event.node.id,
            event.name,
        )

    def _activity_completed(
        self,
        event: LifecycleEvent,
    ) -> None:

        duration = event.node.duration_ms or 0

        self._renderer.spinner_success(
            event.node.id,
            f"{event.name} ({duration} ms)",
        )

    def _activity_failed(
        self,
        event: LifecycleEvent,
    ) -> None:

        duration = event.node.duration_ms or 0

        self._renderer.spinner_error(
            event.node.id,
            f"{event.name} ({duration} ms)",
        )

    def _end_step(
        self,
        event: LifecycleEvent,
    ) -> None:

        index = event.node.get("index")
        total = event.node.get("total")

        if index == total:

            self._renderer.blank()

            self._renderer.rule()
