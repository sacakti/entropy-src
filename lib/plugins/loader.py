"""
Plugin loader.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path
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
            plugin.qualified_name,
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

        plugin_directory = plugin.module_file.parent

        qualified_name = plugin.qualified_name

        try:

            self._ensure_package(
                qualified_name,
                plugin_directory,
            )

            module_name = f"{qualified_name}.plugin"

            spec = importlib.util.spec_from_file_location(
                module_name,
                plugin.module_file,
            )

            if spec is None or spec.loader is None:

                raise PluginLoadError(
                    f"Unable to import plugin " f"'{qualified_name}'.",
                )

            module = importlib.util.module_from_spec(
                spec,
            )

            sys.modules[module_name] = module

            spec.loader.exec_module(
                module,
            )

            return module

        except PluginLoadError:

            raise

        except Exception as exc:

            # import traceback

            raise PluginLoadError(
                f"Unable to load plugin " f"'{qualified_name}'.\n",
                #    f"Exception : {traceback.print_exc()}"
            ) from exc

    def _find_plugin_class(
        self,
        module: ModuleType,
        identifier: str,
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
                identifier,
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

    @staticmethod
    def _ensure_package(
        qualified_name: str,
        plugin_directory: Path,
    ) -> None:
        """
        Ensure the plugin package hierarchy exists.

        The plugin loader dynamically imports plugins, so Python
        cannot rely on the normal filesystem package discovery
        mechanism.
        """

        parts = qualified_name.split(
            ".",
        )

        parent_name = ""

        for index, part in enumerate(
            parts,
        ):

            parent_name = f"{parent_name}.{part}" if parent_name else part

            if parent_name in sys.modules:

                continue

            if index == len(parts) - 1:

                package_path = plugin_directory

            else:

                package_path = plugin_directory.parents[len(parts) - index - 1]

            module = ModuleType(
                parent_name,
            )

            module.__path__ = [
                str(
                    package_path,
                ),
            ]

            module.__package__ = parent_name

            sys.modules[parent_name] = module

    def load_local(
        self,
        directory: Path,
    ) -> type[BasePlugin]:

        directory = directory.expanduser().resolve()

        if not directory.is_dir():

            raise PluginLoadError(
                f"Local plugin directory " f"'{directory}' does not exist.",
            )

        module_file = directory / "plugin.py"

        if not module_file.is_file():

            raise PluginLoadError(
                f"Local plugin module " f"'{module_file}' does not exist.",
            )

        module = self._load_local_module(
            module_file,
        )

        return self._find_plugin_class(
            module,
            str(directory),
        )

    def _load_local_module(
        self,
        module_file: Path,
    ) -> ModuleType:
        """
        Import a local plugin as a package.

        The local plugin directory becomes a temporary package so
        that plugin.py can use relative imports of sibling modules.
        """

        directory = module_file.parent

        identifier = hashlib.sha256(
            str(directory).encode(
                "utf-8",
            ),
        ).hexdigest()[:16]

        package_name = f"entropy_local_{identifier}"

        module_name = f"{package_name}.plugin"

        try:

            #
            # Create the temporary package namespace.
            #

            package = sys.modules.get(
                package_name,
            )

            if package is None:

                package = ModuleType(
                    package_name,
                )

                package.__path__ = [
                    str(directory),
                ]

                package.__package__ = package_name

                sys.modules[package_name] = package

            #
            # Import plugin.py as package.plugin.
            #

            spec = importlib.util.spec_from_file_location(
                module_name,
                module_file,
                submodule_search_locations=None,
            )

            if spec is None or spec.loader is None:

                raise PluginLoadError(
                    f"Unable to import local plugin " f"'{directory}'.",
                )

            module = importlib.util.module_from_spec(
                spec,
            )

            module.__package__ = package_name

            sys.modules[module_name] = module

            spec.loader.exec_module(
                module,
            )

            return module

        except PluginLoadError:

            raise

        except Exception as exc:

            raise PluginLoadError(
                f"Unable to load local plugin " f"'{directory}'.",
            ) from exc
