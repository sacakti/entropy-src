"""
rsync plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class RsyncPluginException(
    PluginException,
):
    """
    Base exception for the rsync plugin.
    """
