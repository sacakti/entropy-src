"""
Base plugin class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.context import EntropyContext


class BasePlugin(ABC):
    """
    Base class for all Entropy plugins.
    """

    def __init__(self, context: EntropyContext):

        self.context = context

    @property
    def output(self):
        return self.context.output

    @property
    def executor(self):
        return self.context.executor

    @abstractmethod
    def execute(self, config: dict[str, Any]) -> bool:
        """
        Execute the plugin.

        Returns
        -------
        bool
            True if the plugin completed successfully.
        """