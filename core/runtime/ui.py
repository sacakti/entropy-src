"""
Workflow execution UI.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from core.ui import UIManager


class ExecutionUI:
    """
    UI facade exposed to workflow plugins.

    Delegates rendering to the application UI while persisting
    replayable workflow UI operations.
    """

    def __init__(
        self,
        ui: UIManager,
        context,
    ) -> None:

        self._ui = ui
        self._context = context

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def print(
        self,
        message: str = "",
    ) -> None:

        self._ui.print(
            message,
        )

        self._persist(
            "print",
            {
                "message": message,
            },
        )

    def rule(
        self,
        title: str = "",
    ) -> None:

        self._ui.rule(
            title,
        )

        self._persist(
            "rule",
            {
                "title": title,
            },
        )

    def panel(
        self,
        title: str,
        lines: Sequence[str],
    ) -> None:

        materialized_lines = list(
            lines,
        )

        self._ui.panel(
            title,
            materialized_lines,
        )

        self._persist(
            "panel",
            {
                "title": title,
                "lines": materialized_lines,
            },
        )

    def table(
        self,
        title: str,
        columns: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:

        materialized_columns = list(
            columns,
        )

        materialized_rows = [
            list(row)
            for row in rows
        ]

        self._ui.table(
            title,
            materialized_columns,
            materialized_rows,
        )

        self._persist(
            "table",
            {
                "title": title,
                "columns": materialized_columns,
                "rows": materialized_rows,
            },
        )

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def prompt(
        self,
        message: str,
        password: bool = False,
    ) -> str:

        return self._ui.prompt(
            message,
            password,
        )

    def confirm(
        self,
        message: str,
    ) -> bool:

        return self._ui.confirm(
            message,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(
        self,
        render_type: str,
        payload: dict,
    ) -> None:

        execution = self._context.execution

        job_id = execution.get(
            "job_id",
        )

        if job_id is None:
            return

        jobs = self._context._entropy.workflow_job_manager

        if jobs is None:
            return

        node = self._context.node

        payload = {
            "type": render_type,
            **payload,
        }

        jobs.event(
            job_id=job_id,
            execution_id=execution.id,
            event_type="render",
            source="workflow",
            node_type=(
                node.type.value
                if node is not None
                else None
            ),
            node_id=(
                node.id
                if node is not None
                else None
            ),
            node_name=(
                node.name
                if node is not None
                else None
            ),
            payload=payload,
        )
