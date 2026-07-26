"""
Entropy Console Manager

All terminal output should go through this class.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)


class ConsoleManager:

    def __init__(self):
        self.console = Console()

    # ----------------------------------------------------
    # Basic Messages
    # ----------------------------------------------------

    def info(self, message: str):
        self.console.print(f"[cyan][INFO][/cyan] {message}")

    def success(self, message: str):
        self.console.print(f"[green][SUCCESS][/green] {message}")

    def warning(self, message: str):
        self.console.print(f"[yellow][WARNING][/yellow] {message}")

    def error(self, message: str):
        self.console.print(f"[red][ERROR][/red] {message}")

    # ----------------------------------------------------
    # Banner
    # ----------------------------------------------------

    def banner(self, title: str, version: str):

        panel = Panel.fit(
            f"[bold cyan]{title}[/bold cyan]\nVersion : {version}",
            title="Deployment Framework",
            border_style="bright_blue",
        )

        self.console.print(panel)

    # ----------------------------------------------------
    # Section
    # ----------------------------------------------------

    def section(self, title: str):

        self.console.rule(f"[bold green]{title}")

    # ----------------------------------------------------
    # Table
    # ----------------------------------------------------

    def table(self, title: str, columns: list, rows: list):

        table = Table(title=title)

        for column in columns:
            table.add_column(column)

        for row in rows:
            table.add_row(*[str(i) for i in row])

        self.console.print(table)

    # ----------------------------------------------------
    # Progress
    # ----------------------------------------------------

    def progress(self):

        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
        )


console = ConsoleManager()