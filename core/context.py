"""
Application runtime context.
"""

from __future__ import annotations

from typing import Optional

from lib.output import output


class EntropyContext:
    """
    Shared runtime context.

    This object is passed across the application instead of
    passing multiple objects individually.
    """

    def __init__(self):

        #
        # Application configuration
        #
        self.config = None

        #
        # Output manager
        #
        self.output = output

        #
        # Current workflow
        #
        self.workflow: Optional[dict] = None

        #
        # Current release
        #
        self.release = None

        #
        # Plugin manager
        #
        self.plugin_manager = None

        #
        # Linux Executor
        #
        self.executor = None