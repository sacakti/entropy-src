"""
User input.
"""

from __future__ import annotations

from typing import cast

import questionary
from rich.console import Console
from rich.prompt import Confirm, Prompt

from core.exceptions import EntropyException


class UserInputCancelledError(
    EntropyException,
):
    """
    Raised when the user cancels interactive input.
    """

    def __init__(self) -> None:

        super().__init__(
            "Input cancelled.",
        )


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

        try:

            if password:

                value = questionary.password(
                    f"{message}:",
                ).ask()

                if value is None:

                    raise UserInputCancelledError()

                return value

            return cast(
                str,
                Prompt.ask(
                    message,
                    console=self._console,
                ),
            )

        except KeyboardInterrupt as exc:

            raise UserInputCancelledError() from exc

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
