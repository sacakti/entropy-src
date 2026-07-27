"""
Plugin loader.

Responsible for importing and caching plugin instances.
"""

from __future__ import annotations

import importlib

from core.context import EntropyContext

from .base import BasePlugin
from .exception import (
    PluginNotFoundError,
    PluginValidationError,
)
from .registry import PluginRegistry


class PluginLoader:
    """
    Loads and caches plugin instances.
    """

    def __init__(
        self,
        context: EntropyContext,
        registry: PluginRegistry,
    ) -> None:

        self.context = context
        self.registry = registry

        self._cache: dict[str, BasePlugin] = {}

    def load(
        self,
        name: str,
    ) -> BasePlugin:
        """
        Load a plugin instance.
        """

        if name in self._cache:
            return self._cache[name]

        metadata = self.registry.get(name)

        if metadata is None:
            raise PluginNotFoundError(
                f"Unknown plugin '{name}'."
            )

        module_name = (
            f"{metadata.package}.{metadata.name}.plugin"
        )

        self.context.output.plugin.debug(
            f"Importing module: {module_name}"
        )

        try:
            module = importlib.import_module(
                metadata.module
            )

        except ModuleNotFoundError as exc:

            #
            # Plugin module does not exist.
            #
            if exc.name == module_name:

                raise PluginNotFoundError(
                    f"Plugin module '{module_name}' not found."
                ) from exc

            #
            # Dependency inside the plugin failed.
            #
            raise

        try:
            class_name = module.PLUGIN_CLASS

        except AttributeError as exc:

            raise PluginValidationError(
                f"{module_name} does not define PLUGIN_CLASS."
            ) from exc

        try:
            plugin_class = getattr(
                module,
                class_name,
            )

        except AttributeError as exc:

            raise PluginValidationError(
                f"Plugin class '{class_name}' not found."
            ) from exc

        if not issubclass(
            plugin_class,
            BasePlugin,
        ):

            raise PluginValidationError(
                f"{class_name} must inherit BasePlugin."
            )

        instance = plugin_class(
            self.context
        )

        self._cache[name] = instance

        return instance

    def has(
        self,
        name: str,
    ) -> bool:
        """
        Return True if the plugin is cached.
        """

        return name in self._cache

    def get(
        self,
        name: str,
    ) -> BasePlugin | None:
        """
        Return a cached plugin instance.
        """

        return self._cache.get(name)

    def clear(self) -> None:
        """
        Clear the plugin instance cache.
        """

        self._cache.clear()

    def list(self) -> list[BasePlugin]:
        """
        Return cached plugin instances.
        """

        return list(
            self._cache.values()
        )