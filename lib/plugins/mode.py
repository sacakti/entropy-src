"""
Plugin execution modes.
"""

from __future__ import annotations

from enum import Enum


class PluginMode(Enum):
    """
    Indicates how a plugin is being executed.
    """

    CLI = "cli"

    WORKFLOW = "workflow"
