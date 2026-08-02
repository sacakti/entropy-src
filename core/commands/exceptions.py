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

        super().__init__(
            "Unknown command '{0}'.".format(
                command,
            )
        )


class CommandAlreadyExistsError(CommandError):

    def __init__(
        self,
        command: str,
    ) -> None:

        super().__init__(
            "Command '{0}' is already registered.".format(
                command,
            )
        )
