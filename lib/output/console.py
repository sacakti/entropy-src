"""
Rich console rendering.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table

from core.constants import CONSOLE_LEVELS

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
        self._level = "NORMAL"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def initialize(
        self,
        level: str = "NORMAL",
    ):
        self._level = level.upper()

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
    # Console Filtering
    # ------------------------------------------------------------------

    def should_emit(
        self,
        level: str,
    ) -> bool:

        mapping = {
            "SUCCESS": "NORMAL",
            "WARNING": "NORMAL",
            "ERROR": "NORMAL",
            "INFO": "VERBOSE",
            "DEBUG": "DEBUG",
        }

        message_level = mapping.get(level.upper(), "NORMAL")

        return (
            CONSOLE_LEVELS[self._level]
            >=
            CONSOLE_LEVELS[message_level]
        )

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

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def prompt(
        self,
        message: str,
        default: str | None = None,
        password: bool = False,
    ) -> str:

        return Prompt.ask(
            message,
            default=default,
            password=password,
        )


    def confirm(
        self,
        message: str,
        default: bool = False,
    ) -> bool:

        return Confirm.ask(
            message,
            default=default,
        )

    # ------------------------------------------------------------------
    # Panel
    # ------------------------------------------------------------------

    def panel(
        self,
        title: str,
        lines: list[str],
        style: str = Theme.INFO,
    ) -> None:

        content = "\n".join(lines)

        self.console.print(
            Panel(
                content,
                title=title,
                border_style=style,
                expand=False,
            )
        )
