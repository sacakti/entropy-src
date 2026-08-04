"""
Generator exceptions.
"""

from core.exceptions import EntropyException


class GeneratorError(
    EntropyException,
):
    """
    Base generator exception.
    """


class GeneratorNotFoundError(
    GeneratorError,
):
    """
    Unknown generator.
    """

    def __init__(
        self,
        name: str,
    ) -> None:

        super().__init__(
            f"Unknown generator '{name}'.",
        )


class GeneratorValidationError(
    GeneratorError,
):
    """
    Generator validation failed.
    """


class GeneratorAlreadyExistsError(
    GeneratorValidationError,
):
    """
    Generated artifact already exists.
    """


class InvalidGeneratorNameError(
    GeneratorValidationError,
):
    """
    Invalid generator name.
    """
