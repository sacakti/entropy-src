"""
consolidate.images exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class ConsolidationException(
    PluginException,
):
    """
    Base exception for the consolidate.images plugin.
    """


class ConsolidationReleaseError(
    ConsolidationException,
):
    """
    A release package is missing, unreadable, or its image has no Dockerfile.
    """


class ConsolidationIndexError(
    ConsolidationException,
):
    """
    The YAML repository's resource index is missing or unreadable.
    """
