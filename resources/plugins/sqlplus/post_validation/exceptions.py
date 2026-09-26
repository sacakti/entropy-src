"""
post_validation plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class PostValidationPluginException(
    PluginException,
):
    """
    Base exception for the post_validation plugin.
    """
