"""
Plugin manager.

Responsible for loading and caching plugin instances.
"""

from __future__ import annotations

import importlib
from time import perf_counter

from core.constants import SEARCH_PATHS
from core.context import EntropyContext

from .base import BasePlugin
from .exception import (
    PluginError,
    PluginExecutionError,
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

        for package in SEARCH_PATHS:
            module_name = f"{package}.{name}"

            try:
                module = importlib.import_module(module_name)
                break

            except ModuleNotFoundError as exc:
                if exc.name == module_name:
                    continue
                raise
        else:
            raise PluginNotFoundError(
                f"Unknown plugin '{name}'"
            )

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

        if not issubclass(plugin_class, BasePlugin):
            raise PluginValidationError(
                f"{class_name} must inherit BasePlugin."
            )

        plugin = plugin_class(self.context)

        self._cache[name] = plugin

        return plugin

    def execute(
        self,
        name: str,
        config: dict,
    ) -> float:
        """
        Validate and execute a plugin.

        Returns
        -------
        float
            Execution duration in seconds.
        """

        plugin = self.load(name)

        #
        # Validate configuration
        #
        plugin.validate(config)

        start = perf_counter()

        try:
            plugin.execute(config)

        except PluginError:
            raise

        except Exception as exc:
            raise PluginExecutionError(
                f"Plugin '{name}' execution failed."
            ) from exc

        finally:
            duration = perf_counter() - start

        self.context.output.plugin.success(
            f"Plugin '{name}' completed "
            f"({duration:.2f}s)"
        )

        return duration