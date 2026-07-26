"""
Plugin exceptions.
"""


class PluginError(Exception):
    """Base class for all plugin-related errors."""


class PluginNotFoundError(PluginError):
    """Raised when a plugin cannot be found."""


class PluginValidationError(PluginError):
    """Raised when a plugin is invalid."""


class PluginExecutionError(PluginError):
    """Raised when plugin execution fails."""