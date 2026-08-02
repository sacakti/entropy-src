"""
Rich console sink.
"""

from __future__ import annotations

from rich.progress import TaskID

from ..event import BaseEvent, Event
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

        self._tasks: dict[str, TaskID] = {}

    # ------------------------------------------------------------------
    # Sink
    # ------------------------------------------------------------------

    def publish(
        self,
        event: BaseEvent,
    ) -> None:

        if not isinstance(event, Event):
            return

        handler = getattr(
            self,
            f"_{event.type.name.lower()}",
            None,
        )

        if handler is not None:
            handler(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _indent(
        self,
        event: Event,
    ) -> str:

        #
        # Workflow = 0
        # Step     = 1
        # Stage    = 2
        # Activity = 3
        #

        return "    " * event.node.depth

    def _message(
        self,
        event: Event,
    ) -> str:

        return f"{self._indent(event)}{event.name}"

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execution_started(
        self,
        event: Event,
    ) -> None:

        self._renderer.info(f"Execution started : {event.name}")

    def _execution_completed(
        self,
        event: Event,
    ) -> None:

        self._renderer.success(f"Execution completed : {event.name}")

    def _execution_failed(
        self,
        event: Event,
    ) -> None:

        self._renderer.error(f"Execution failed : {event.name}")

    def _execution_cancelled(
        self,
        event: Event,
    ) -> None:

        self._renderer.warning(f"Execution cancelled : {event.name}")

    # ------------------------------------------------------------------
    # Step
    # ------------------------------------------------------------------

    def _step_started(
        self,
        event: Event,
    ) -> None:

        self._renderer.blank()

        self._renderer.rule()

        self._renderer.heading(
            event.name,
        )

    def _step_completed(
        self,
        event: Event,
    ) -> None:

        pass

    def _step_failed(
        self,
        event: Event,
    ) -> None:

        pass

    def _step_skipped(
        self,
        event: Event,
    ) -> None:

        self._renderer.warning(
            self._message(event),
        )

    # ------------------------------------------------------------------
    # Stage
    # ------------------------------------------------------------------

    def _stage_started(
        self,
        event: Event,
    ) -> None:

        self._renderer.heading(
            self._message(event),
        )

    def _stage_completed(
        self,
        event: Event,
    ) -> None:

        self._renderer.success(
            self._message(event),
        )

    def _stage_failed(
        self,
        event: Event,
    ) -> None:

        self._renderer.error(
            self._message(event),
        )

    # ------------------------------------------------------------------
    # Activity
    # ------------------------------------------------------------------

    def _activity_started(
        self,
        event: Event,
    ) -> None:

        task = self._renderer.spinner(
            self._message(event),
        )

        self._tasks[event.node.id] = task

    def _activity_completed(
        self,
        event: Event,
    ) -> None:

        task = self._tasks.pop(
            event.node.id,
            None,
        )

        self._renderer.spinner_success(
            task,
            self._message(event),
        )

    def _activity_failed(
        self,
        event: Event,
    ) -> None:

        task = self._tasks.pop(
            event.node.id,
            None,
        )

        self._renderer.spinner_error(
            task,
            self._message(event),
        )
