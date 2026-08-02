"""
Plugin base class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .exceptions import PluginNotImplementedError
from .metadata import PluginMetadata

if TYPE_CHECKING:
    from core.runtime.context import ExecutionContext
    from lib.models.workflow import WorkflowStep


class Plugin(ABC):
    """
    Base class for all plugins.
    """

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """
        Plugin metadata.
        """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(
        self,
        context: ExecutionContext,
    ) -> None:
        """
        Initialize plugin resources.
        """

    def validate(
        self,
        step: WorkflowStep,
    ) -> None:
        """
        Validate workflow step configuration.
        """

    @abstractmethod
    def execute(
        self,
        context: ExecutionContext,
        step: WorkflowStep,
    ) -> None:
        """
        Execute the plugin.
        """

        raise PluginNotImplementedError("Plugin execution has not been implemented.")

    def dispose(
        self,
    ) -> None:
        """
        Dispose plugin resources.
        """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(
        self,
        context: ExecutionContext,
        step: WorkflowStep,
    ) -> None:
        """
        Execute the complete plugin lifecycle.
        """

        self.initialize(context)

        try:

            self.validate(step)

            self.execute(
                context,
                step,
            )

        finally:

            self.dispose()

    # ------------------------------------------------------------------
    # Extension Points
    # ------------------------------------------------------------------

    def commands(self) -> list:
        """
        CLI commands exposed by the plugin.
        """

        return []

    def generators(self) -> list:
        """
        Template generators exposed by the plugin.
        """

        return []

    def hooks(self) -> list:
        """
        Runtime hooks exposed by the plugin.
        """

        return []
