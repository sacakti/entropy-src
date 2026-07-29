"""
Rich console rendering.
"""

from __future__ import annotations

from typing import Any, cast

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn
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
    ) -> None:
        self._level = level.upper()

    def _start_progress(self) -> None:

        if not self._started:
            self._progress.start()
            self._started = True

    def _finish_progress(
        self,
        task_id: TaskID | None,
    ) -> None:

        if task_id is not None:
            self._progress.remove_task(task_id)

        if not self._progress.tasks:
            self._progress.stop()
            self._started = False

    def shutdown(self) -> None:

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

        return CONSOLE_LEVELS[self._level] >= CONSOLE_LEVELS[message_level]

    # ------------------------------------------------------------------
    # Spinner
    # ------------------------------------------------------------------

    def progress(
        self,
        message: str,
    ) -> TaskID:

        self._start_progress()

        return self._progress.add_task(
            f"[cyan]{message}",
            total=None,
        )

    def success(
        self,
        message: str,
        task_id: TaskID | None = None,
    ) -> None:

        self._finish_progress(task_id)

        self.console.print(f"[{Theme.SUCCESS}]✔[/] {message}")

    def warning(
        self,
        message: str,
        task_id: TaskID | None = None,
    ) -> None:

        self._finish_progress(task_id)

        self.console.print(f"[{Theme.WARNING}]⚠[/] {message}")

    def error(
        self,
        message: str,
        task_id: TaskID | None = None,
    ) -> None:

        self._finish_progress(task_id)

        self.console.print(f"[{Theme.ERROR}]✖[/] {message}")

    # ------------------------------------------------------------------
    # Information
    # ------------------------------------------------------------------

    def info(self, message: str) -> None:

        self.console.print(f"[{Theme.INFO}]ℹ[/] {message}")

    def debug(self, message: str) -> None:

        self.console.print(f"[{Theme.DEBUG}]•[/] {message}")

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def step(
        self,
        step_no: int,
        title: str,
    ) -> None:

        self.console.print()

        self.console.print(Rule(style="bright_black"))

        self.console.print(f"[bold cyan]▶ Step {step_no} : {title}[/]")

    def sub(self, message: str) -> None:

        self.console.print(f"    {message}")

    # ------------------------------------------------------------------
    # Generic
    # ------------------------------------------------------------------

    def banner(self, banner: Any) -> None:

        self.console.print(banner)

    def print(self, *args: Any, **kwargs: Any) -> None:

        self.console.print(*args, **kwargs)

    def rule(self, title="") -> None:

        self.console.rule(title)

    def table(
        self,
        title: str,
        columns: list[str],
        rows: list[list[Any]],
    ) -> None:

        table = Table(title=title)

        for column in columns:
            table.add_column(column)

        for row in rows:
            table.add_row(*[str(item) for item in row])

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

        if default is None:
            return Prompt.ask(
                message,
                password=password,
            )

        return Prompt.ask(
            message,
            default=cast(str, default),
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
