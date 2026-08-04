"""
Plugin manager.
"""

from __future__ import annotations

from pathlib import Path

from core.context import EntropyContext

from lib.database.repositories.plugin_registry import PluginRepository
from lib.models.plugin import Plugin

from .discovery import PluginDiscovery
from .installer import PluginInstaller
from .loader import PluginLoader
from .manifest import ManifestReader
from .registry import PluginRegistry
from .runner import PluginRunner
from .validator import ManifestValidator


class PluginManager:
    """
    Plugin subsystem.

    Responsible for orchestrating plugin installation,
    discovery, loading and execution.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.database_manager is not None
        assert context.extension_manager is not None
        assert context.migration_manager is not None

        #
        # Persistence
        #

        self._repository = PluginRepository(
            context.database_manager.connection,
        )

        #
        # Runtime
        #

        self._registry = PluginRegistry()

        self._discovery = PluginDiscovery(
            self._repository,
            self._registry,
        )

        self._loader = PluginLoader(
            context,
            self._registry,
        )

        self._runner = PluginRunner(
            self._loader,
        )

        #
        # Installation
        #

        self._reader = ManifestReader(
            context,
        )

        self._validator = ManifestValidator()

        self._installer = PluginInstaller(
            context=context,
            repository=self._repository,
            reader=self._reader,
            validator=self._validator,
            extensions=context.extension_manager,
            migrations=context.migration_manager,
        )

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def install(
        self,
        directory: Path,
        *,
        reinstall: bool = False,
    ) -> Plugin:
        """
        Install a plugin.
        """

        plugin = self._installer.install(
            directory,
            reinstall=reinstall,
        )

        self.refresh()

        return plugin

    def uninstall(
        self,
        qualified_name: str,
    ) -> None:
        """
        Uninstall a plugin.
        """

        plugin = self._repository.get_by_qualified_name(
            qualified_name,
        )

        self._installer.uninstall(
            plugin,
        )

        self.refresh()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
    ) -> None:
        """
        Discover installed plugins.
        """

        self._discovery.discover()

    def refresh(
        self,
    ) -> None:
        """
        Refresh the runtime registry.
        """

        self._loader.clear()

        self._discovery.discover()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def exists(
        self,
        qualified_name: str,
    ) -> bool:
        """
        Return True if a plugin is installed.
        """

        namespace, name = qualified_name.split(
            ".",
            1,
        )

        return self._repository.exists(
            namespace,
            name,
        )

    def list(
        self,
    ) -> list[Plugin]:
        """
        Return installed plugins.
        """

        return self._repository.list()

    def get(
        self,
        qualified_name: str,
    ) -> Plugin:
        """
        Return an installed plugin.
        """

        return self._repository.get_by_qualified_name(
            qualified_name,
        )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    def load(
        self,
        qualified_name: str,
    ):
        """
        Load a plugin.
        """

        return self._loader.load(
            qualified_name,
        )

    def run(
        self,
        qualified_name: str,
        arguments: dict[str, object],
    ) -> None:
        """
        Execute a plugin.
        """

        self._runner.run(
            qualified_name,
            arguments,
        )

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def clear(
        self,
    ) -> None:
        """
        Clear the runtime cache.
        """

        self._loader.clear()

        self._registry.clear()
