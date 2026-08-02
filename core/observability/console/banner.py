"""
Application banner.
"""

from rich.align import Align
from rich.panel import Panel
from rich.text import Text

from .theme import ConsoleTheme

class Banner:
    """Builds the application banner."""

    @staticmethod
    def build(application: str, version: str):
        logo = r"""
███████╗███╗   ██╗████████╗██████╗  ██████╗ ██████╗ ██╗   ██╗
██╔════╝████╗  ██║╚══██╔══╝██╔══██╗██╔═══██╗██╔══██╗╚██╗ ██╔╝
█████╗  ██╔██╗ ██║   ██║   ██████╔╝██║   ██║██████╔╝ ╚████╔╝
██╔══╝  ██║╚██╗██║   ██║   ██╔══██╗██║   ██║██╔═══╝   ╚██╔╝
███████╗██║ ╚████║   ██║   ██║  ██║╚██████╔╝██║        ██║
╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝        ╚═╝
"""

        text = Text()

        text.append(logo, style="bold bright_cyan")
        text.append("\n")

        text.append(
            f"{application}\n",
            style=f"bold {ConsoleTheme.PRIMARY}",
        )

        text.append(
            f"Version {version}",
            style=ConsoleTheme.MUTED,
        )

        panel = Panel(
            text,
            border_style=ConsoleTheme.PRIMARY,
            expand=False,
            padding=(1, 4),
        )

        return Align.center(panel)
