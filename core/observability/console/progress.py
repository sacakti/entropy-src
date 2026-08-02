"""
Rich progress manager.
"""

from __future__ import annotations

from rich.console import Console
from rich.progress import Progress
from rich.progress import SpinnerColumn
from rich.progress import TaskID
from rich.progress import TextColumn


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
            SpinnerColumn(style="cyan"),
            TextColumn("{task.description}"),
            transient=True,
            console=console,
        )

        self._started = False

        self._tasks: dict[str, TaskID] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:

        if self._started:

            self._progress.stop()

            self._started = False

            self._tasks.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start(self) -> None:

        if not self._started:

            self._progress.start()

            self._started = True

    def _finish(
        self,
        node_id: str,
    ) -> None:

        task = self._tasks.pop(
            node_id,
            None,
        )

        if task is not None:

            self._progress.remove_task(task)

        if not self._tasks and self._started:

            self._progress.stop()

            self._started = False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def start(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._start()

        self._tasks[node_id] = self._progress.add_task(
            f"[cyan]{message}",
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

        self._progress.console.print(
            f"[green]✔[/] {message}"
        )

    def warning(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._finish(
            node_id,
        )

        self._progress.console.print(
            f"[yellow]⚠[/] {message}"
        )

    def error(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._finish(
            node_id,
        )

        self._progress.console.print(
            f"[red]✖[/] {message}"
        )
