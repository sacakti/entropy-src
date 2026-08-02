"""
Plugin loader.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from .exceptions import (
    PluginNotFoundError,
    PluginValidationError,
)
from .plugin import Plugin
from .registry import PluginRegistry

if TYPE_CHECKING:
    from core.context import EntropyContext


class PluginLoader:
    """
    Loads plugin instances.
    """

    def __init__(
        self,
        context: "EntropyContext",
        registry: PluginRegistry,
    ) -> None:

        self._context = context

        self._registry = registry

        self._cache: dict[str, Plugin] = {}

    # ------------------------------------------------------------------

    def load(
        self,
        name: str,
    ) -> Plugin:

        if name in self._cache:

            return self._cache[name]

        metadata = self._registry.resolve(
            name,
        )

        try:

            module = importlib.import_module(
                metadata.module,
            )

        except ModuleNotFoundError as exc:

            raise PluginNotFoundError(
                name,
            ) from exc

        try:

            class_name = module.PLUGIN_CLASS

            plugin_class = getattr(
                module,
                class_name,
            )

        except AttributeError as exc:

            raise PluginValidationError(
                name,
                [
                    "PLUGIN_CLASS is missing.",
                ],
            ) from exc

        if not issubclass(
            plugin_class,
            Plugin,
        ):

            raise PluginValidationError(
                name,
                [
                    f"{class_name} must inherit Plugin.",
                ],
            )

        instance = plugin_class()

        self._cache[
            name
        ] = instance

        return instance

    # ------------------------------------------------------------------

    def clear(
        self,
    ) -> None:

        self._cache.clear()

    def has(
        self,
        name: str,
    ) -> bool:

        return name in self._cache

    def get(
        self,
        name: str,
    ) -> Plugin | None:

        return self._cache.get(name)

    def list(
        self,
    ) -> list[Plugin]:

        return list(
            self._cache.values(),
        )
