"""
OpenShift pod logs plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class PodLogsException(
    PluginException,
):
    """
    Base exception for the pod logs plugin.
    """
