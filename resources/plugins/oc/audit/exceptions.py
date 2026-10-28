"""
audit plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class AuditPluginException(
    PluginException,
):
    """
    Base exception for the audit plugin.
    """
