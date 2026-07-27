"""
Command exceptions.
"""


class CommandError(Exception):
    """Base command exception."""


class CommandNotFoundError(CommandError):

    def __init__(self, command: str):

        super().__init__(
            f"Unknown command '{command}'."
        )