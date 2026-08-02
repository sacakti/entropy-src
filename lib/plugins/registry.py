"""
Plugin registry.
"""

from __future__ import annotations

from .exceptions import (
    PluginAlreadyRegisteredError,
    PluginNotFoundError,
)
from .metadata import PluginMetadata


class PluginRegistry:
    """
    Stores plugin metadata.
    """

    def __init__(self) -> None:

        self._plugins: dict[str, PluginMetadata] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        metadata: PluginMetadata,
    ) -> None:

        if metadata.name in self._plugins:

            raise PluginAlreadyRegisteredError(
                metadata.name,
            )

        self._plugins[
            metadata.name
        ] = metadata

    # ------------------------------------------------------------------

    def resolve(
        self,
        name: str,
    ) -> PluginMetadata:

        try:

            return self._plugins[name]

        except KeyError as exc:

            raise PluginNotFoundError(
                name,
            ) from exc

    # ------------------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> PluginMetadata | None:

        return self._plugins.get(name)

    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[PluginMetadata]:

        return sorted(
            self._plugins.values(),
            key=lambda plugin: plugin.name,
        )

    # ------------------------------------------------------------------

    def has(
        self,
        name: str,
    ) -> bool:

        return name in self._plugins

    # ------------------------------------------------------------------

    def clear(
        self,
    ) -> None:

        self._plugins.clear()

    # ------------------------------------------------------------------

    def __len__(
        self,
    ) -> int:

        return len(
            self._plugins,
        )

    def __contains__(
        self,
        name: str,
    ) -> bool:

        return self.has(name)
