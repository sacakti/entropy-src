"""
Docker clean plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class CleanPluginException(
    PluginException,
):
    """
    Base exception for the Docker clean plugin.
    """
