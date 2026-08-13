"""
Base exceptions for the plugins module.
"""

from core.exceptions import EntropyException


class PluginException(EntropyException):
    """
    Base exception for the plugins module.
    """


class PluginNotFoundError(PluginException):
    """
    Raised when a plugin is not found.
    """


class PluginManifestNotFoundError(PluginException):
    """
    Raised when a plugin manifest is not found.
    """


class PluginValidationError(PluginException):
    """
    Raised when a plugin manifest is invalid.
    """


class PluginAlreadyInstalledError(PluginException):
    """
    Raised when a plugin is already installed.
    """


class PluginClassNotFoundError(PluginException):
    """
    Raised when a plugin class is not found in the plugin module.
    """


class PluginLoadError(PluginException):
    """
    Raised when a plugin fails to load.
    """

class PluginVersionError(PluginException):
    """
    Raised when plugin version is empty.
    """

class PluginInvalidRequirementError(PluginException):
    """
    Raised when plugin requirement is not supported.
    """

class PluginValueError(PluginException):
    """
    Raised plugin value error.
    """
    def __init__(
        self,
        message: str,
    ) -> None:

        super().__init__(
            message,
        )

class InvalidPluginNameError(
    PluginException,
):
    """
    Raised when a plugin qualified name is invalid.
    """

    def __init__(
        self,
        qualified_name: str,
    ) -> None:

        super().__init__(
            f"Invalid plugin name '{qualified_name}'. "
            "Expected format: '<namespace>.<name>'.",
        )

class PluginDisabledError(
    PluginException,
):
    """
    Raised when attempting to execute a disabled plugin.
    """

    def __init__(
        self,
        qualified_name: str,
    ) -> None:

        super().__init__(
            f"Plugin '{qualified_name}' is disabled.",
        )

class PluginExecutionError(
    PluginException,
):
    """Raised when plugin execution violates the plugin contract."""
