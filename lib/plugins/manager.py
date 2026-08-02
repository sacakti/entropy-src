"""
Plugin manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.runtime.context import ExecutionContext
from lib.models.workflow import WorkflowStep

from .discovery import PluginDiscovery
from .loader import PluginLoader
from .metadata import PluginMetadata
from .plugin import Plugin
from .registry import PluginRegistry

if TYPE_CHECKING:
    from core.context import EntropyContext


class PluginManager:
    """
    Plugin framework.

    Responsible for:

        • discovery
        • registration
        • loading

    Plugin execution is performed by the Workflow runtime.
    """

    def __init__(
        self,
        context: "EntropyContext",
    ) -> None:

        self._registry = PluginRegistry()

        self._loader = PluginLoader(
            context,
            self._registry,
        )

        self._discovery = PluginDiscovery(
            context,
            self._registry,
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
    ) -> None:

        self._discovery.discover()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        metadata: PluginMetadata,
    ) -> None:

        self._registry.register(
            metadata,
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def resolve(
        self,
        name: str,
    ) -> PluginMetadata:

        return self._registry.resolve(
            name,
        )

    def get(
        self,
        name: str,
    ) -> PluginMetadata | None:

        return self._registry.get(
            name,
        )

    def list(
        self,
    ) -> list[PluginMetadata]:

        return self._registry.list()

    def has(
        self,
        name: str,
    ) -> bool:

        return self._registry.has(
            name,
        )

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(
        self,
        name: str,
    ) -> Plugin:

        return self._loader.load(
            name,
        )

    def loaded(
        self,
        name: str,
    ) -> bool:

        return self._loader.has(
            name,
        )

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def clear(
        self,
    ) -> None:

        self._loader.clear()

        self._registry.clear()

    # ------------------------------------------------------------------
    # Execute
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
    # Helpers
    # ------------------------------------------------------------------

    def __len__(
        self,
    ) -> int:

        return len(
            self._registry,
        )

    def __contains__(
        self,
        name: str,
    ) -> bool:

        return self.has(
            name,
        )
