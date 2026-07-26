"""
Application banner.
"""

from rich.align import Align
from rich.panel import Panel
from rich.text import Text


class Banner:
    """Builds the application banner."""

    @staticmethod
    def build(app_name: str, version: str):
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
            f"{app_name}\n",
            style="bold white",
        )

        text.append(
            f"Version {version}",
            style="green",
        )

        return Panel(
            Align.center(text),
            border_style="bright_blue",
            expand=True,
            padding=(1, 2),
        )