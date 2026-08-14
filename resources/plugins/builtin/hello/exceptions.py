"""
Hello plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class HelloException(
    PluginException,
):
    """
    Base exception for the Hello plugin.
    """
