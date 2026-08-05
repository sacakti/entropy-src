"""
Base plugin.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.runtime.context import ExecutionContext


class BasePlugin(ABC):
    """
    Base class for all Entropy plugins.

    A plugin implements one unit of executable
    workflow behaviour.
    """

    def __init__(
        self,
        context: ExecutionContext,
    ) -> None:

        self._context = context

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def context(
        self,
    ) -> ExecutionContext:
        """
        Current workflow execution context.
        """

        return self._context

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(
        self,
    ) -> None:
        """
        Execute the plugin.
        """

        raise NotImplementedError()
