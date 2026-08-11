"""
Plugin loader.
"""

from __future__ import annotations

import importlib.util
import inspect
from types import ModuleType

from lib.models.plugin import Plugin

from .base import BasePlugin
from .exceptions import (
    PluginClassNotFoundError,
    PluginLoadError,
)
from .registry import PluginRegistry


class PluginLoader:
    """
    Loads plugin implementations.

    Responsible only for importing plugin modules
    and locating the plugin class.

    Plugin instances are created by PluginRunner.
    """

    def __init__(
        self,
        registry: PluginRegistry,
    ) -> None:

        self._registry = registry

        self._cache: dict[
            int,
            type[BasePlugin],
        ] = {}

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def load(
        self,
        qualified_name: str,
    ) -> type[BasePlugin]:
        """
        Load a plugin class.
        """

        plugin = self._plugin(
            qualified_name,
        )

        assert plugin.id is not None

        cached = self._cache.get(
            plugin.id,
        )

        if cached is not None:

            return cached

        plugin_class = self._load_class(
            plugin,
        )

        self._cache[plugin.id] = plugin_class

        return plugin_class

    def loaded(
        self,
        qualified_name: str,
    ) -> bool:
        """
        Return True if a plugin class is already loaded.
        """

        plugin = self._plugin(
            qualified_name,
        )

        assert plugin.id is not None

        return plugin.id in self._cache

    def clear(
        self,
    ) -> None:
        """
        Clear loaded plugin classes.
        """

        self._cache.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_class(
        self,
        plugin: Plugin,
    ) -> type[BasePlugin]:
        """
        Import a plugin module and locate its plugin class.
        """

        module = self._load_module(
            plugin,
        )

        return self._find_plugin_class(
            module,
            plugin,
        )

    def _load_module(
        self,
        plugin: Plugin,
    ) -> ModuleType:
        """
        Import a plugin module.
        """

        if not plugin.module_file.exists():

            raise PluginLoadError(
                f"Plugin module '{plugin.module_file}' does not exist.",
            )

        spec = importlib.util.spec_from_file_location(
            plugin.qualified_name,
            plugin.module_file,
        )

        if spec is None or spec.loader is None:

            raise PluginLoadError(
                f"Unable to import plugin " f"'{plugin.qualified_name}'.",
            )

        try:

            module = importlib.util.module_from_spec(
                spec,
            )

            spec.loader.exec_module(
                module,
            )

        except Exception as exc:

            raise PluginLoadError(
                f"Unable to load plugin " f"'{plugin.qualified_name}'.",
            ) from exc

        return module

    def _find_plugin_class(
        self,
        module: ModuleType,
        plugin: Plugin,
    ) -> type[BasePlugin]:
        """
        Locate the plugin implementation.
        """

        classes = [
            cls
            for _, cls in inspect.getmembers(
                module,
                inspect.isclass,
            )
            if (
                issubclass(
                    cls,
                    BasePlugin,
                )
                and cls is not BasePlugin
            )
        ]

        if (
            len(
                classes,
            )
            != 1
        ):

            raise PluginClassNotFoundError(
                plugin.qualified_name,
            )

        return classes[0]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _plugin(
        self,
        qualified_name: str,
    ) -> Plugin:

        return self._registry.resolve(
            qualified_name,
        )

    def get(
        self,
        qualified_name: str,
    ) -> Plugin:
        """
        Return registered plugin metadata.
        """

        return self._plugin(
            qualified_name,
        )
