"""
Rich console rendering.
"""

from __future__ import annotations

from rich.console import Console
from rich.progress import Progress
from rich.progress import SpinnerColumn
from rich.progress import TextColumn
from rich.table import Table
from rich.rule import Rule

from .theme import Theme


class ConsoleEngine:

    def __init__(self):

        self.console = Console()

        self._progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("{task.description}"),
            transient=True,
            console=self.console,
        )

        self._started = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_progress(self):

        if not self._started:
            self._progress.start()
            self._started = True

    def _finish_progress(self, task_id: int | None):

        if task_id is not None:
            self._progress.remove_task(task_id)

        if not self._progress.tasks:
            self._progress.stop()
            self._started = False

    def shutdown(self):

        if self._started:
            self._progress.stop()
            self._started = False

    # ------------------------------------------------------------------
    # Spinner
    # ------------------------------------------------------------------

    def progress(self, message: str):

        self._start_progress()

        task_id = self._progress.add_task(
            f"[cyan]{message}",
            total=None,
        )

        return task_id

    def success(
        self,
        message: str,
        task_id: int | None = None,
    ):

        self._finish_progress(task_id)

        self.console.print(
            f"[{Theme.SUCCESS}]✔[/] {message}"
        )


    def warning(
        self,
        message: str,
        task_id: int | None = None,
    ):

        self._finish_progress(task_id)

        self.console.print(
            f"[{Theme.WARNING}]⚠[/] {message}"
        )


    def error(
        self,
        message: str,
        task_id: int | None = None,
    ):

        self._finish_progress(task_id)

        self.console.print(
            f"[{Theme.ERROR}]✖[/] {message}"
        )

    # ------------------------------------------------------------------
    # Information
    # ------------------------------------------------------------------

    def info(self, message: str):

        self.console.print(
            f"[{Theme.INFO}]ℹ[/] {message}"
        )

    def debug(self, message: str):

        self.console.print(
            f"[{Theme.DEBUG}]•[/] {message}"
        )

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def step(
        self,
        step_no: int,
        title: str,
    ):

        self.console.print()

        self.console.print(
            Rule(style="bright_black")
        )

        self.console.print(
            f"[bold cyan]▶ Step {step_no} : {title}[/]"
        )

    def sub(self, message: str):

        self.console.print(
            f"    {message}"
        )

    # ------------------------------------------------------------------
    # Generic
    # ------------------------------------------------------------------

    def banner(self, banner):

        self.console.print(banner)

    def print(self, *args, **kwargs):

        self.console.print(*args, **kwargs)

    def rule(self, title=""):

        self.console.rule(title)

    def table(
        self,
        title,
        columns,
        rows,
    ):

        table = Table(title=title)

        for column in columns:
            table.add_column(column)

        for row in rows:
            table.add_row(
                *[str(item) for item in row]
            )

        self.console.print(table)