"""
OpenShift pod metrics plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class PodMetricsException(
    PluginException,
):
    """
    Base exception for the pod metrics plugin.
    """
