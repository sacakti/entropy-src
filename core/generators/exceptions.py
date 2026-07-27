"""
Generator exceptions.
"""


class GeneratorError(Exception):
    """Base generator exception."""


class GeneratorNotFoundError(GeneratorError):

    def __init__(self, generator: str):

        super().__init__(
            f"Unknown generator '{generator}'."
        )