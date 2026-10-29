"""
load_data plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class LoadDataPluginException(PluginException):
    """
    Base exception for load_data plugin failures.
    """
