"""
Base plugin.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.context import EntropyContext


class BasePlugin(ABC):
    """
    Base class for all Entropy plugins.

    A plugin implements one unit of executable
    workflow behaviour.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        self._context = context

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(
        self,
        **kwargs,
    ) -> None:
        """
        Execute the plugin.
        """

        raise NotImplementedError()
