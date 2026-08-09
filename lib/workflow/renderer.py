"""
Workflow event renderer.
"""

from __future__ import annotations

from core.models.enums import EventType
from core.ui import UIManager

from lib.workflow.jobs.events import WorkflowEvent


class WorkflowEventRenderer:
    """
    Renders persisted workflow events using the application UI.

    The renderer is responsible only for presentation. It does not
    access the database and does not know how events are consumed.
    """

    def __init__(
        self,
        ui: UIManager,
    ) -> None:

        self._ui = ui

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(
        self,
        event: WorkflowEvent,
    ) -> None:
        """
        Render one persisted workflow event.
        """

        #
        # Runtime message.
        #

        if event.event_type == "message":

            self._message(
                event,
            )

            return

        #
        # Future structured UI events.
        #

        if event.event_type == "render":

            self._render(
                event,
            )

            return

        #
        # Lifecycle event.
        #

        try:

            event_type = EventType(
                event.event_type,
            )

        except ValueError:

            self._ui.info(
                event.message or event.event_type,
            )

            return

        handlers = {
            EventType.EXECUTION_STARTED:
                self._execution_started,

            EventType.EXECUTION_COMPLETED:
                self._execution_completed,

            EventType.EXECUTION_FAILED:
                self._execution_failed,

            EventType.EXECUTION_CANCELLED:
                self._execution_cancelled,

            EventType.STEP_STARTED:
                self._step_started,

            EventType.STEP_COMPLETED:
                self._step_completed,

            EventType.STEP_FAILED:
                self._step_failed,

            EventType.STEP_SKIPPED:
                self._step_skipped,

            EventType.STAGE_STARTED:
                self._stage_started,

            EventType.STAGE_COMPLETED:
                self._stage_completed,

            EventType.STAGE_FAILED:
                self._stage_failed,

            EventType.ACTIVITY_STARTED:
                self._activity_started,

            EventType.ACTIVITY_COMPLETED:
                self._activity_completed,

            EventType.ACTIVITY_FAILED:
                self._activity_failed,
        }

        handler = handlers.get(
            event_type,
        )

        if handler is not None:

            handler(
                event,
            )

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def _execution_started(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._ui.info(
            f"Execution started : "
            f"{event.node_name or 'Workflow'}",
        )

    def _execution_completed(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._success(
            event,
            (
                f"Execution completed : "
                f"{event.node_name or 'Workflow'}"
            ),
        )

    def _execution_failed(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._error(
            event,
            (
                f"Execution failed : "
                f"{event.node_name or 'Workflow'}"
            ),
        )

    def _execution_cancelled(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._ui.warning(
            (
                f"Execution cancelled : "
                f"{event.node_name or 'Workflow'}"
            ),
        )

    # ------------------------------------------------------------------
    # Step
    # ------------------------------------------------------------------

    def _step_started(
        self,
        event: WorkflowEvent,
    ) -> None:

        metadata = self._metadata(
            event,
        )

        index = metadata.get(
            "index",
            "?",
        )

        total = metadata.get(
            "total",
            "?",
        )

        self._ui.print(
            "",
        )

        self._ui.rule()

        self._ui.print(
            f"[bold]Step {index}/{total} : "
            f"{event.node_name}[/]",
        )

    def _step_completed(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._ui.success(
            self._step_label_with_duration(
                event,
            ),
        )

        self._end_step(
            event,
        )

    def _step_failed(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._ui.error(
            self._step_label_with_duration(
                event,
            ),
        )

        self._end_step(
            event,
        )

    def _step_skipped(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._ui.warning(
            self._step_label(
                event,
            ),
        )

        self._end_step(
            event,
        )

    def _end_step(
        self,
        event: WorkflowEvent,
    ) -> None:

        metadata = self._metadata(
            event,
        )

        index = metadata.get(
            "index",
        )

        total = metadata.get(
            "total",
        )

        if index == total:

            self._ui.print(
                "",
            )

            self._ui.rule()

    def _step_label_with_duration(
        self,
        event: WorkflowEvent,
    ) -> str:

        label = self._step_label(
            event,
        )

        payload = event.payload or {}

        duration = payload.get(
            "duration_ms",
        )

        if duration is not None:

            label = (
                f"{label} "
                f"({duration} ms)"
            )

        return label

    # ------------------------------------------------------------------
    # Stage
    # ------------------------------------------------------------------

    def _stage_started(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._ui.print(
            f"▶ {event.node_name}",
        )

    def _stage_completed(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._success(
            event,
            event.node_name or "Stage",
        )

    def _stage_failed(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._error(
            event,
            event.node_name or "Stage",
        )

    # ------------------------------------------------------------------
    # Activity
    # ------------------------------------------------------------------

    def _activity_started(
        self,
        event: WorkflowEvent,
    ) -> None:

        return

    def _activity_completed(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._success(
            event,
            event.node_name or "Activity",
        )

    def _activity_failed(
        self,
        event: WorkflowEvent,
    ) -> None:

        self._error(
            event,
            event.node_name or "Activity",
        )

    # ------------------------------------------------------------------
    # Message
    # ------------------------------------------------------------------

    def _message(
        self,
        event: WorkflowEvent,
    ) -> None:

        message = event.message or ""

        level = (
            event.level or "INFO"
        ).upper()

        if level == "ERROR":

            self._ui.error(
                message,
            )

            return

        if level in (
            "WARNING",
            "WARN",
        ):

            self._ui.warning(
                message,
            )

            return

        if level == "SUCCESS":

            self._ui.success(
                message,
            )

            return

        self._ui.info(
            message,
        )

    # ------------------------------------------------------------------
    # Structured rendering
    # ------------------------------------------------------------------

    def _render(
        self,
        event: WorkflowEvent,
    ) -> None:
        """
        Render a structured persisted UI event.

        Structured rendering will be populated as the corresponding
        event payloads are introduced into the workflow event stream.
        """

        payload = event.payload or {}

        render_type = payload.get(
            "type",
        )

        if render_type == "table":

            self._ui.table(
                title=payload.get(
                    "title",
                    "",
                ),
                columns=payload.get(
                    "columns",
                    [],
                ),
                rows=payload.get(
                    "rows",
                    [],
                ),
            )

            return

        if render_type == "panel":

            self._ui.panel(
                title=payload.get(
                    "title",
                    "",
                ),
                lines=payload.get(
                    "lines",
                    [],
                ),
            )

            return

        if render_type == "rule":

            self._ui.rule(
                payload.get(
                    "title",
                    "",
                ),
            )

            return

        if render_type == "print":

            self._ui.print(
                payload.get(
                    "message",
                    "",
                ),
            )

            return

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _metadata(
        event: WorkflowEvent,
    ) -> dict:

        payload = event.payload or {}

        metadata = payload.get(
            "metadata",
            {},
        )

        if isinstance(
            metadata,
            dict,
        ):

            return metadata

        return {}

    def _step_label(
        self,
        event: WorkflowEvent,
    ) -> str:

        metadata = self._metadata(
            event,
        )

        index = metadata.get(
            "index",
        )

        total = metadata.get(
            "total",
        )

        if index is not None and total is not None:

            return (
                f"Step {index}/{total} : "
                f"{event.node_name}"
            )

        return (
            event.node_name
            or "Workflow step"
        )

    def _success(
        self,
        event: WorkflowEvent,
        label: str,
    ) -> None:

        payload = event.payload or {}

        duration = payload.get(
            "duration_ms",
        )

        if duration is not None:

            label = (
                f"{label} "
                f"({duration} ms)"
            )

        self._ui.success(
            label,
        )

    def _error(
        self,
        event: WorkflowEvent,
        label: str,
    ) -> None:

        payload = event.payload or {}

        duration = payload.get(
            "duration_ms",
        )

        if duration is not None:

            label = (
                f"{label} "
                f"({duration} ms)"
            )

        self._ui.error(
            label,
        )

