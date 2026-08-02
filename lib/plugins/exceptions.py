"""
Plugin exceptions.
"""

from __future__ import annotations

from core.exceptions import EntropyException


class PluginError(EntropyException):
    """
    Base class for all plugin errors.
    """


class PluginNotFoundError(PluginError):
    """
    Plugin not found.
    """

    def __init__(
        self,
        plugin: str,
    ) -> None:

        super().__init__(f"Plugin '{plugin}' was not found.")


class PluginAlreadyRegisteredError(
    PluginError,
):
    """
    Plugin already registered.
    """

    def __init__(
        self,
        plugin: str,
    ) -> None:

        super().__init__(f"Plugin '{plugin}' is already registered.")


class PluginValidationError(
    PluginError,
):
    """
    Plugin validation failed.
    """

    def __init__(
        self,
        plugin: str,
        errors: list[str],
    ) -> None:

        message = f"Plugin '{plugin}' is invalid:\n" + "\n".join(f"  • {error}" for error in errors)

        super().__init__(message)


class PluginExecutionError(
    PluginError,
):
    """
    Plugin execution failed.
    """

    def __init__(
        self,
        plugin: str,
        message: str,
    ) -> None:

        super().__init__(f"Plugin '{plugin}' execution failed: {message}")


class PluginNotImplementedError(
    PluginError,
):
    """
    Plugin method not implemented.
    """

    def __init__(
        self,
        message: str = "Plugin method has not been implemented.",
    ) -> None:

        super().__init__(message)
