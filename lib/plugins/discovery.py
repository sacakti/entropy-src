"""
Plugin discovery.
"""

from __future__ import annotations

from lib.database.repositories.plugin_registry import (
    PluginRepository,
)

from .registry import PluginRegistry


class PluginDiscovery:
    """
    Discovers installed plugins.

    Responsible for loading installed plugins
    from the repository into the runtime registry.
    """

    def __init__(
        self,
        repository: PluginRepository,
        registry: PluginRegistry,
    ) -> None:

        self._repository = repository

        self._registry = registry

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
    ) -> None:
        """
        Discover installed plugins.
        """

        self._registry.clear()

        for plugin in self._repository.list():

            if not plugin.enabled:

                continue

            self._registry.register(
                plugin,
            )
