"""
Command exceptions.
"""

from core.exceptions import EntropyException


class CommandError(EntropyException):
    """
    Base command exception.
    """


class CommandNotFoundError(CommandError):

    def __init__(
        self,
        command: str,
    ) -> None:

        super().__init__(f"Unknown command '{command}'.")


class CommandAlreadyExistsError(CommandError):

    def __init__(
        self,
        command: str,
    ) -> None:

        super().__init__(f"Command '{command}' is already registered.")
