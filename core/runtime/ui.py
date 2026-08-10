"""
Workflow execution UI.
"""

from __future__ import annotations

import multiprocessing
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

        if self._interactive():

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

        if self._interactive():

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

        if self._interactive():

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

        materialized_rows = [list(row) for row in rows]

        if self._interactive():

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
    # Progress
    # ------------------------------------------------------------------

    def progress(
        self,
        description: str,
        total: int | None = None,
    ):
        """
        Create a progress indicator.

        Progress rendering is delegated to the application UI.
        """

        return self._ui.progress(
            description,
            total,
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
            node_type=(node.type.value if node is not None else None),
            node_id=(node.id if node is not None else None),
            node_name=(node.name if node is not None else None),
            payload=payload,
        )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _interactive(
        self,
    ) -> bool:
        """
        Return True when execution is attached to the
        interactive foreground process.
        """

        return multiprocessing.current_process().name == "MainProcess"
