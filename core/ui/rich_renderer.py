"""
Rich UI renderer.
"""

from __future__ import annotations

from getpass import getpass
from typing import Iterable
from typing import Optional
from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table

from .renderer import Renderer


class RichRenderer(Renderer):
    """
    Rich-based renderer.
    """

    def __init__(self) -> None:

        self._console = Console()

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def print(
        self,
        message: str = "",
    ) -> None:

        self._console.print(
            message,
        )

    def rule(
        self,
        title: str = "",
    ) -> None:

        self._console.print(
            Rule(title),
        )

    def banner(
        self,
        application: str,
        version: str,
    ) -> None:

        self.rule()

        self._console.print(
            "[bold cyan]{0}[/bold cyan] [green]{1}[/green]".format(
                application,
                version,
            ),
        )

        self.rule()

    def panel(
        self,
        title: str,
        lines: Sequence[str],
    ) -> None:

        self._console.print(
            Panel(
                "\n".join(lines),
                title=title,
                expand=False,
            ),
        )

    def table(
        self,
        title: str,
        columns: Sequence[str],
        rows: Iterable[Sequence[str]],
    ) -> None:

        table = Table(
            title=title,
        )

        for column in columns:

            table.add_column(
                column,
            )

        for row in rows:

            table.add_row(
                *[str(value) for value in row],
            )

        self._console.print(
            table,
        )

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def prompt(
        self,
        message: str,
        password: bool = False,
    ) -> str:

        if password:

            return getpass(
                "{0}: ".format(
                    message,
                )
            )

        return Prompt.ask(
            message,
            console=self._console,
        )

    def confirm(
        self,
        message: str,
    ) -> bool:

        return Confirm.ask(
            message,
            console=self._console,
        )

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def progress(
        self,
        description: str,
        total: Optional[int] = None,
    ):

        raise NotImplementedError(
            "Progress support is not implemented."
        )

    # ------------------------------------------------------------------
    # Property
    # ------------------------------------------------------------------

    @property
    def console(self):
        """
        Rich console.
        """

        return self._console
