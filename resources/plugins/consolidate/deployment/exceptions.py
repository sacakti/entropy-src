"""
consolidate.deployment exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class ConsolidationException(
    PluginException,
):
    """
    Base exception for the consolidate.deployment plugin.
    """


class ConsolidationReleaseError(
    ConsolidationException,
):
    """
    A release package is missing, unreadable, or has an unexpected layout.
    """


class ConsolidationDefinitionError(
    ConsolidationException,
):
    """
    A Deployment change in a release is malformed or cannot follow an earlier one.
    """
