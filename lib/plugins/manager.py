"""
Plugin manager.

Responsible for loading and caching plugin instances.
"""

from __future__ import annotations

import importlib

from core.constants import SEARCH_PATHS
from core.context import EntropyContext

from .base import BasePlugin
from .exception import (
    PluginNotFoundError,
    PluginValidationError,
)


class PluginManager:
    """
    Loads and manages Entropy plugins.
    """

    def __init__(self, context: EntropyContext):

        self.context = context
        self._cache: dict[str, BasePlugin] = {}

    def has(self, name: str) -> bool:
        """
        Return True if the plugin is already cached.
        """

        return name in self._cache

    def clear_cache(self) -> None:
        """
        Clear all cached plugin instances.
        """

        self._cache.clear()

    def load(self, name: str) -> BasePlugin:
        """
        Load a plugin.
        """

        if name in self._cache:
            return self._cache[name]

        # module_name = f"plugins.{name}"

        # class_name = (
        #     "".join(
        #         part.capitalize()
        #         for part in name.split("_")
        #     )
        #     + "Plugin"
        # )

        for package in SEARCH_PATHS:
            module_name = f"{package}.{name}"

            try:
                module = importlib.import_module(module_name)
                break

            except ModuleNotFoundError as exc:
                # Ignore only if the missing module is the plugin itself.
                if exc.name == module_name:
                    continue
                raise
        else:
            raise PluginNotFoundError(f"Unknown plugin '{name}'")

        # try:
        #     module = importlib.import_module(module_name)

        # except ImportError as exc:
        #     raise PluginNotFoundError(
        #         f"Unknown plugin '{name}'"
        #     ) from exc

        # try:
        #     plugin_class = getattr(module, class_name)

        # except AttributeError as exc:
        #     raise PluginValidationError(
        #         f"Plugin class '{class_name}' not found."
        #     ) from exc

        # if not issubclass(plugin_class, BasePlugin):
        #     raise PluginValidationError(
        #         f"{class_name} must inherit BasePlugin."
        #     )

        try:
            class_name = module.PLUGIN_CLASS
        except AttributeError as exc:
            raise PluginValidationError(
                f"{module.__name__} does not define PLUGIN_CLASS."
            ) from exc

        try:
            plugin_class = getattr(module, class_name)
        except AttributeError as exc:
            raise PluginValidationError(
                f"Plugin class '{class_name}' not found."
            ) from exc

        plugin = plugin_class(self.context)

        self._cache[name] = plugin

        return plugin

    def execute(
        self,
        name: str,
        config: dict,
    ) -> None:
        """
        Execute a plugin.
        """

        plugin = self.load(name)

        plugin.execute(config)