"""
Plugin runtime registry.
"""

from __future__ import annotations

from lib.models.plugin import Plugin
from lib.plugins.exceptions import PluginNotFoundError


class PluginRegistry:
    """
    In-memory plugin registry.

    Responsible for storing installed plugins
    during the current Entropy session.
    """

    def __init__(
        self,
    ) -> None:

        self._plugins: dict[
            str,
            Plugin,
        ] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        plugin: Plugin,
    ) -> None:
        """
        Register a plugin.
        """

        self._plugins[
            plugin.qualified_name
        ] = plugin

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def resolve(
        self,
        qualified_name: str,
    ) -> Plugin:
        """
        Return a registered plugin.

        Raises
        ------
        PluginNotFoundError
            If the plugin is not registered.
        """

        plugin = self.get(
            qualified_name,
        )

        if plugin is None:

            raise PluginNotFoundError(
                qualified_name,
            )

        return plugin

    def get(
        self,
        qualified_name: str,
    ) -> Plugin | None:
        """
        Return a plugin if registered.
        """

        return self._plugins.get(
            qualified_name,
        )

    def has(
        self,
        qualified_name: str,
    ) -> bool:
        """
        Return True if the plugin is registered.
        """

        return (
            qualified_name
            in self._plugins
        )

    def list(
        self,
    ) -> list[Plugin]:
        """
        Return registered plugins.
        """

        return sorted(
            self._plugins.values(),
            key=lambda plugin: (
                plugin.namespace,
                plugin.name,
            ),
        )

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def clear(
        self,
    ) -> None:
        """
        Clear the registry.
        """

        self._plugins.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __contains__(
        self,
        qualified_name: str,
    ) -> bool:

        return self.has(
            qualified_name,
        )

    def __len__(
        self,
    ) -> int:

        return len(
            self._plugins,
        )
