"""
User input.
"""

from __future__ import annotations

from getpass import getpass

from rich.console import Console
from rich.prompt import Confirm, Prompt


class PromptManager:
    """
    Interactive user input.
    """

    def __init__(
        self,
        console: Console,
    ) -> None:

        self._console = console

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def prompt(
        self,
        message: str,
        password: bool = False,
    ) -> str:
        """
        Prompt for user input.
        """

        if password:

            return getpass(f"{message}: ")

        return Prompt.ask(
            message,
            console=self._console,
        )

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------

    def confirm(
        self,
        message: str,
    ) -> bool:
        """
        Prompt for confirmation.
        """

        return Confirm.ask(
            message,
            console=self._console,
        )
