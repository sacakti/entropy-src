"""
Process monitor plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class ProcessMonitorException(
    PluginException,
):
    """
    Base exception for the process monitor plugin.
    """
