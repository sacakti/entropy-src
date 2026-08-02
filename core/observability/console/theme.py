"""
Console color theme.
"""

from __future__ import annotations


class ConsoleTheme:
    """
    Console theme.

    Centralized Rich color definitions.
    """

    # ------------------------------------------------------------------
    # Branding
    # ------------------------------------------------------------------

    PRIMARY = "cyan"

    SECONDARY = "bright_blue"

    ACCENT = "magenta"

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    SUCCESS = "green"

    WARNING = "yellow"

    ERROR = "red"

    INFO = "cyan"

    DEBUG = "bright_black"

    # ------------------------------------------------------------------
    # Text
    # ------------------------------------------------------------------

    TEXT = "white"

    MUTED = "grey70"

    DIM = "grey50"

    # ------------------------------------------------------------------
    # Borders
    # ------------------------------------------------------------------

    BORDER = "bright_black"

    PANEL = "cyan"

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    SPINNER = "cyan"

    COMPLETED = "green"

    FAILED = "red"

    SKIPPED = "yellow"
