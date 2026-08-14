"""
Rich UI renderer.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from getpass import getpass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
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
            f"[bold cyan]{application}[/bold cyan] [green]{version}[/green]",
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
    # Documentation
    # ------------------------------------------------------------------

    def markdown(
        self,
        content: str,
        *,
        pager: bool = False,
    ) -> None:
        """
        Render Markdown content.

        When pager is enabled, Rich displays the rendered
        Markdown through the configured terminal pager.
        """

        document = Markdown(
            content,
            code_theme="monokai",
            hyperlinks=True,
        )

        if pager:

            with self._console.pager():

                self._console.print(
                    document,
                )

            return

        self._console.print(
            document,
        )

    def editor(
        self,
        content: str,
        *,
        filename: str = "workflow.json",
    ) -> str:
        """
        Open content in the user's configured editor.

        Returns the edited content. If the editor exits without
        changing the file, the original content is returned.
        """

        editor = os.environ.get(
            "EDITOR",
            "vi",
        )

        suffix = (
            Path(
                filename,
            ).suffix
            or ".json"
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=suffix,
            delete=False,
        ) as temporary:

            temporary.write(
                content,
            )

            path = Path(
                temporary.name,
            )

        try:

            result = subprocess.run(
                [
                    editor,
                    str(path),
                ],
                check=False,
            )

            if result.returncode != 0:

                raise RuntimeError(
                    f"Editor '{editor}' exited with " f"status {result.returncode}.",
                )

            edited = path.read_text(
                encoding="utf-8",
            )

            return edited

        finally:

            path.unlink(
                missing_ok=True,
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

            return getpass(f"{message}: ")

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

        raise NotImplementedError("Progress support is not implemented.")

    # ------------------------------------------------------------------
    # Property
    # ------------------------------------------------------------------

    @property
    def console(self):
        """
        Rich console.
        """

        return self._console

    def info(
        self,
        message: str,
    ) -> None:
        """
        Display an informational message.
        """

        self.print(
            f"[cyan]ℹ[/] {message}",
        )

    def success(
        self,
        message: str,
    ) -> None:
        """
        Display a success message.
        """

        self.print(
            f"[green]✔[/] {message}",
        )

    def warning(
        self,
        message: str,
    ) -> None:
        """
        Display a warning message.
        """

        self.print(
            f"[yellow]⚠[/] {message}",
        )

    def error(
        self,
        message: str,
    ) -> None:
        """
        Display an error message.
        """

        self.print(
            f"[red]✖[/] {message}",
        )
