"""
Application runtime context.
"""

from __future__ import annotations

from typing import Optional

from lib.models.workflow import WorkflowDefinition
from lib.output import manager


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
        self.output = manager

        #
        # Current workflow
        #
        # self.workflow: Optional[dict] = None
        self.workflow: Optional[WorkflowDefinition] = None

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

        #
        # Database manager
        #
        self.database_manager = None
