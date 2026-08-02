"""
Rich console renderer.

Pure rendering layer.

Contains no runtime logic.
Contains no observability logic.
Contains no workflow logic.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .banner import Banner
from .progress import ProgressManager
from .theme import ConsoleTheme


class ConsoleRenderer:
    """
    Rich console renderer.

    Responsible only for rendering.
    """

    def __init__(self) -> None:

        self._console = Console()

        self._progress = ProgressManager(
            self._console,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:

        self._progress.shutdown()

    # ------------------------------------------------------------------
    # Banner
    # ------------------------------------------------------------------

    def banner(
        self,
        application: str,
        version: str,
    ) -> None:

        self._console.print(
            Banner.build(
                application,
                version,
            )
        )

    # ------------------------------------------------------------------
    # Headings
    # ------------------------------------------------------------------

    def heading(
        self,
        title: str,
    ) -> None:

        self._console.print()

        self._console.print(
            Rule(
                style="bright_black",
            )
        )

        self._console.print(
            f"[bold cyan]▶ {title}[/]"
        )

    def rule(
        self,
        title: str = "",
    ) -> None:

        self._console.rule(title)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def info(
        self,
        message: str,
    ) -> None:

        self._console.print(
            f"[{ConsoleTheme.INFO}]ℹ[/] {message}"
        )

    def success(
        self,
        message: str,
    ) -> None:

        self._console.print(
            f"[{ConsoleTheme.SUCCESS}]✔[/] {message}"
        )

    def warning(
        self,
        message: str,
    ) -> None:

        self._console.print(
            f"[{ConsoleTheme.WARNING}]⚠[/] {message}"
        )

    def error(
        self,
        message: str,
    ) -> None:

        self._console.print(
            f"[{ConsoleTheme.ERROR}]✖[/] {message}"
        )

    def debug(
        self,
        message: str,
    ) -> None:

        self._console.print(
            f"[{ConsoleTheme.DEBUG}]•[/] {message}"
        )

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def spinner(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._progress.start(
            node_id=node_id,
            message=message,
        )

    def spinner_success(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._progress.success(
            node_id=node_id,
            message=message,
        )

    def spinner_warning(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._progress.warning(
            node_id=node_id,
            message=message,
        )

    def spinner_error(
        self,
        node_id: str,
        message: str,
    ) -> None:

        self._progress.error(
            node_id=node_id,
            message=message,
        )

    # ------------------------------------------------------------------
    # Panels
    # ------------------------------------------------------------------

    def panel(
        self,
        title: str,
        lines: list[str],
        style: str = ConsoleTheme.INFO,
    ) -> None:

        self._console.print(
            Panel(
                "\n".join(lines),
                title=title,
                border_style=style,
                expand=False,
            )
        )

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def table(
        self,
        title: str,
        columns: list[str],
        rows: list[list[Any]],
    ) -> None:

        table = Table(
            title=title,
        )

        for column in columns:

            table.add_column(column)

        for row in rows:

            table.add_row(
                *[str(item) for item in row]
            )

        self._console.print(table)

    # ------------------------------------------------------------------
    # Generic
    # ------------------------------------------------------------------

    def print(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:

        self._console.print(
            *args,
            **kwargs,
        )

    def text(
        self,
        content: str,
        style: str | None = None,
    ) -> None:

        self._console.print(
            Text(
                content,
                style=style,
            )
        )

    def blank(
        self,
        lines: int = 1,
    ) -> None:

        for _ in range(lines):

            self._console.print()

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
    # Advanced
    # ------------------------------------------------------------------

    @property
    def console(self) -> Console:

        return self._console
