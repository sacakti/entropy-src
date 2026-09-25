"""
invalid_objects_report plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class InvalidObjectsReportPluginException(
    PluginException,
):
    """
    Base exception for the invalid_objects_report plugin.
    """
