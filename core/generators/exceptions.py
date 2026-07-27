"""
Generator exceptions.
"""


class GeneratorError(Exception):
    """Base generator exception."""

class InvalidGeneratorError(GeneratorError):
    """Generator validation failed."""


class PluginAlreadyExistsError(InvalidGeneratorError):
    """Plugin already exists."""


class InvalidPluginNameError(InvalidGeneratorError):
    """Invalid plugin name."""

class GeneratorNotFoundError(GeneratorError):

    def __init__(self, generator: str):

        super().__init__(
            f"Unknown generator '{generator}'."
        )