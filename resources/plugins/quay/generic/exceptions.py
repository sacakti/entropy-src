"""
Quay generic plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class QuayPluginException(
    PluginException,
):
    """
    Base exception for the Quay generic plugin.
    """


class QuayRuleError(
    QuayPluginException,
):
    """
    A retention rule is malformed.
    """


class QuayApiError(
    QuayPluginException,
):
    """
    A Quay API request failed; `status` is the HTTP status (0 when unreachable).
    """

    def __init__(
        self,
        message: str,
        status: int = 0,
    ) -> None:

        super().__init__(
            message,
        )

        self.status = status
