"""
Skopeo generic plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class SkopeoPluginException(
    PluginException,
):
    """
    Base exception for the Skopeo generic plugin.
    """


class SkopeoRuleError(
    SkopeoPluginException,
):
    """
    A selection rule is malformed.
    """
