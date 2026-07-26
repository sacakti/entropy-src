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
        self.output = context.output
        self.executor = context.executor

    def validate(
        self,
        config: dict[str, Any],
    ) -> None:
        """
        Validate plugin configuration.

        Plugins may override this method.
        """

        return

    @abstractmethod
    def execute(
        self,
        config: dict[str, Any],
    ) -> None:
        """
        Execute the plugin.
        """