"""
Base plugin.
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod


class Plugin(ABC):

    NAME = ""

    def __init__(self, context):

        self.context = context

    @abstractmethod
    def execute(self, config: dict) -> None:
        """
        Execute the plugin.
        """
        raise NotImplementedError