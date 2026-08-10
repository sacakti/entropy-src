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
