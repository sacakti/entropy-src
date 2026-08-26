"""
cache_refresh plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class CacheRefreshPluginException(PluginException):
    """
    Base exception for cache refresh plugin failures.
    """
