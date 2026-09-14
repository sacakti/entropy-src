"""
generic plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class GenericPluginException(
    PluginException,
):
    """
    Base exception for the generic plugin.
    """


class GenericPluginError(GenericPluginException):
    """
    Generic plugin error
    """
