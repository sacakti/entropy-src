"""
Rich progress manager.
"""

from __future__ import annotations

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn

from .theme import ConsoleTheme


class ProgressManager:
    """
    Manages Rich progress spinners.

    Owns all Rich progress state.
    """

    def __init__(
        self,
        console: Console,
    ) -> None:

        self._progress = Progress(
            SpinnerColumn(
                style=ConsoleTheme.INFO,
            ),
            TextColumn(
                "{task.description}",
            ),
            transient=True,
            console=console,
        )

        self._started = False
        self._task: TaskID | None = None
        self._node_id: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(
        self,
    ) -> None:

        if self._started:

            self._progress.stop()

        self._started = False
        self._task = None
        self._node_id = None

    # ------------------------------------------------------------------
    # Suspension
    # ------------------------------------------------------------------

    def suspend(
        self,
    ) -> None:

        if self._started:
            self._progress.stop()

    def resume(
        self,
    ) -> None:

        if self._started:
            self._progress.start()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start(
        self,
    ) -> None:

        if not self._started:

            self._progress.start()

            self._started = True

    def _finish(
        self,
        node_id: str,
    ) -> None:

        if self._node_id != node_id:
            return

        if self._task is not None:

            self._progress.remove_task(
                self._task,
            )

        self._task = None
        self._node_id = None

        if self._started:

            self._progress.stop()

            self._started = False

    def _print(
        self,
        style: str,
        icon: str,
        message: str,
    ) -> None:

        self._progress.console.print(
            f"[{style}]{icon}[/] {message}",
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def start(
        self,
        node_id: str,
        message: str,
    ) -> None:

        if self._task is not None:

            self._progress.remove_task(
                self._task,
            )

            self._task = None

        self._start()

        self._node_id = node_id

        self._task = self._progress.add_task(
            f"[{ConsoleTheme.INFO}]{message}",
            total=None,
        )

    def success(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._finish(
            node_id,
        )

        self._print(
            ConsoleTheme.SUCCESS,
            "✔",
            message,
        )

    def warning(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._finish(
            node_id,
        )

        self._print(
            ConsoleTheme.WARNING,
            "⚠",
            message,
        )

    def error(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._finish(
            node_id,
        )

        self._print(
            ConsoleTheme.ERROR,
            "✖",
            message,
        )
