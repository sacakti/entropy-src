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
