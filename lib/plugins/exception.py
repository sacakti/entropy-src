"""
Plugin exceptions.
"""

from core.exceptions import EntropyException


class PluginError(EntropyException):
    """Base class for all plugin-related errors."""


class PluginNotFoundError(PluginError):
    """Raised when a plugin cannot be found."""

class PluginValidationError(PluginError):
    """
    Raised when a plugin definition is invalid.
    """

    def __init__(
        self,
        plugin: str,
        errors: list[str],
    ):
        self.plugin = plugin
        self.errors = errors

        message = (
            f"Invalid plugin '{plugin}':\n"
            + "\n".join(f"  - {error}" for error in errors)
        )

        super().__init__(message)

class PluginExecutionError(PluginError):
    """Raised when plugin execution fails."""

class PluginNotImplementedError(PluginError):
    """Raised when a plugin method is not implemented."""

class PluginAlreadyRegisteredError(
    PluginValidationError,
):
    """
    Plugin already registered.
    """
