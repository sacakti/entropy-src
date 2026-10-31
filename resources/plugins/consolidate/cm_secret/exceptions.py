"""
consolidate.cm_secret exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class ConsolidationException(
    PluginException,
):
    """
    Base exception for the consolidate.cm_secret plugin.
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
    A ConfigMap/Secret change in a release is malformed.
    """
