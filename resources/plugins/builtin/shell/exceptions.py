"""
Hello plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class ShellException(
    PluginException,
):
    """
    Base exception for the Shell plugin.
    """
