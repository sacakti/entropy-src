"""
Plugin registry.

Responsible for discovering and registering plugin metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.constants import PLUGIN_DIR
from core.context import EntropyContext

from lib.models.plugin import Plugin

from .exception import PluginAlreadyRegisteredError
from .validators.manifest import ManifestValidator

class PluginRegistry:
    """
    Discovers and registers plugin metadata.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        self.context = context

        self._plugins: dict[str, Plugin] = {}

        self.validator = ManifestValidator()

    def _read_manifest(
        self,
        manifest: Path,
    ) -> dict:
        """
        Read a plugin manifest.
        """

        with open(
            manifest,
            "r",
            encoding="utf-8",
        ) as fp:

            return json.load(fp)

    def discover(self) -> None:

        if not PLUGIN_DIR.exists():
            return

        for namespace in PLUGIN_DIR.iterdir():

            if not namespace.is_dir():
                continue

            self.context.output.plugin.debug(
                f"Searching for plugins in: {namespace}"
            )

            for directory in namespace.iterdir():

                if not directory.is_dir():
                    continue

                plugin = self.validator.validate(
                    namespace.name,
                    directory,
                )

                self.register(plugin)

        self.context.output.plugin.debug(
            f"Discovered {len(self._plugins)} plugin(s)."
        )

    def register(
        self,
        plugin: Plugin,
    ) -> None:
        """
        Register plugin metadata.
        """

        if plugin.name in self._plugins:

            raise PluginAlreadyRegisteredError(
                f"Plugin '{plugin.name}' is already registered."
            )

        self._plugins[plugin.name] = plugin

    def get(
        self,
        name: str,
    ) -> Plugin | None:
        """
        Return plugin metadata.
        """

        return self._plugins.get(name)

    def list(self) -> list[Plugin]:
        """
        Return all registered plugins.
        """

        return list(
            self._plugins.values()
        )

    def clear(self) -> None:
        """
        Remove all registered plugins.
        """

        self._plugins.clear()

    def has(
        self,
        name: str,
    ) -> bool:
        """
        Return True if the plugin is registered.
        """

        return name in self._plugins