from __future__ import annotations

# from abc import ABC, abstractmethod
# from typing import Any
# from core.context import EntropyContext
# from lib.plugins.exception import PluginNotImplementedError
from lib.plugins.exceptions import (
    PluginNotImplementedError,
)


class BasePlugin:

    def __init__(self, context):

        self.context = context

    def initialize(self) -> None:
        """
        Initialize the plugin.
        """

        pass

    def validate(
        self,
        config: dict,
    ) -> None:
        """
        Validate plugin configuration.
        """

        pass

    def execute(
        self,
        config: dict,
    ) -> None:
        """
        Execute the plugin.
        """

        raise PluginNotImplementedError("Plugin execution has not been implemented.")

    def dispose(self) -> None:
        """
        Dispose plugin resources.
        """

        pass

    def commands(self):
        """
        Commands
        """
        return []

    def generators(self):
        """
        Generators
        """
        return []

    def hooks(self):
        """
        Hooks
        """
        return []
