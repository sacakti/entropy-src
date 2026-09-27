"""
sftp plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class SftpPluginException(
    PluginException,
):
    """
    Base exception for the sftp plugin.
    """
