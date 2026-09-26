"""
analyse plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class AnalysePluginException(
    PluginException,
):
    """
    Base exception for the analyse plugin.
    """
