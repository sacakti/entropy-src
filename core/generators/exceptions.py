"""
Generator exceptions.
"""

from core.exceptions import EntropyException


class GeneratorError(EntropyException):
    """Base generator exception."""


class InvalidGeneratorError(GeneratorError):
    """Generator validation failed."""


class PluginAlreadyExistsError(InvalidGeneratorError):
    """Plugin already exists."""


class InvalidPluginNameError(InvalidGeneratorError):
    """Invalid plugin name."""


class GeneratorNotFoundError(GeneratorError):

    def __init__(self, generator: str):

        super().__init__(f"Unknown generator '{generator}'.")
