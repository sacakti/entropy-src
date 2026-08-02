"""
Plugin framework.
"""

from .exceptions import (
    PluginAlreadyRegisteredError,
    PluginError,
    PluginExecutionError,
    PluginNotFoundError,
    PluginValidationError,
)

from .metadata import PluginMetadata
from .plugin import Plugin

__all__ = [
    "Plugin",
    "PluginMetadata",
    "PluginError",
    "PluginNotFoundError",
    "PluginValidationError",
    "PluginExecutionError",
    "PluginAlreadyRegisteredError",
]
