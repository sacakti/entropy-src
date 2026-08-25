"""
Generic Git plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class GenericGitPluginException(
    PluginException,
):
    """
    Base exception for the generic Git plugin.
    """
