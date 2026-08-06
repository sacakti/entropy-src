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

        self._tasks: dict[str, TaskID] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(
        self,
    ) -> None:
        """
        Stop the progress manager.
        """

        if self._started:

            self._progress.stop()

            self._started = False

            self._tasks.clear()

    # ------------------------------------------------------------------
    # Suspension
    # ------------------------------------------------------------------

    def suspend(
        self,
    ) -> None:
        """
        Temporarily suspend progress rendering.

        Used before rendering panels, tables or prompting
        the user so Rich can redraw the spinner afterwards.
        """

        if self._started:

            self._progress.stop()

    def resume(
        self,
    ) -> None:
        """
        Resume progress rendering.
        """

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

        task = self._tasks.pop(
            node_id,
            None,
        )

        if task is not None:

            self._progress.remove_task(
                task,
            )

        if not self._tasks and self._started:

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

        self._start()

        self._tasks[node_id] = self._progress.add_task(
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
