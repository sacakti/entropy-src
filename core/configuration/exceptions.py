"""
Configuration exceptions.
"""

from __future__ import annotations

from core.exceptions import EntropyException


class ConfigurationException(EntropyException):
    """
    Base class for configuration errors.
    """


class ConfigurationFileNotFoundError(ConfigurationException):
    """
    Configuration file does not exist.
    """

    def __init__(
        self,
        file,
    ) -> None:

        super().__init__(
            f"Configuration file not found: {file}"
        )


class UnsupportedConfigurationFormatError(
    ConfigurationException,
):
    """
    Unsupported configuration format.
    """

    def __init__(
        self,
        suffix: str,
    ) -> None:

        super().__init__(
            f"Unsupported configuration format: {suffix}"
        )


class InvalidConfigurationError(
    ConfigurationException,
):
    """
    Invalid configuration.
    """

    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            f"Invalid configuration: {message}"
        )


class ConfigurationNotLoadedError(
    ConfigurationException,
):
    """
    Configuration has not been loaded.
    """

    def __init__(self) -> None:

        super().__init__(
            "Configuration has not been loaded."
        )
