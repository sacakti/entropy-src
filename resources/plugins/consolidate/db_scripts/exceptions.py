"""
consolidate.db_scripts exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class ConsolidationException(
    PluginException,
):
    """
    Base exception for the consolidate.db_scripts plugin.
    """


class ConsolidationReleaseError(
    ConsolidationException,
):
    """
    A release package is missing, unreadable, or lacks a script its plan names.
    """


class ConsolidationDefinitionError(
    ConsolidationException,
):
    """
    A release's execution plan is malformed.
    """
