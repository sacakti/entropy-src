"""
sync_yamls plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class SyncYamlsPluginException(
    PluginException,
):
    """
    Base exception for the sync_yamls plugin.
    """
