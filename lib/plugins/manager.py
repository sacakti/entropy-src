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
    validation, discovery, loading, execution and lifecycle.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.database_manager is not None
        assert context.extension_manager is not None
        assert context.migration_manager is not None
        assert context.observability is not None

        self._context = context

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

        #
        # Observability
        #

        self._events = context.observability.emitter(
            "plugins",
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

        self._events.log.info(
            f"Installing plugin from '{directory}'.",
        )

        plugin = self._installer.install(
            directory,
            reinstall=reinstall,
        )

        self.refresh()

        self._events.log.success(
            f"Plugin '{plugin.qualified_name}' " f"installed successfully.",
        )

        return plugin

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def uninstall(
        self,
        qualified_name: str,
    ) -> None:
        """
        Uninstall a plugin.
        """

        self._events.log.info(
            f"Uninstalling plugin '{qualified_name}'.",
        )

        plugin = self._repository.get_by_qualified_name(
            qualified_name,
        )

        self._installer.uninstall(
            plugin,
        )

        self.refresh()

        self._events.log.success(
            f"Plugin '{qualified_name}' " f"uninstalled successfully.",
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(
        self,
        qualified_name: str,
    ) -> None:
        """
        Verify an installed plugin.
        """

        self._events.log.info(
            f"Verifying plugin '{qualified_name}'.",
        )

        plugin = self._repository.get_by_qualified_name(
            qualified_name,
        )

        self._installer.verify(
            plugin,
        )

        self._events.log.success(
            f"Plugin '{qualified_name}' " f"verified successfully.",
        )

    # ------------------------------------------------------------------
    # Repair
    # ------------------------------------------------------------------

    def repair(
        self,
        qualified_name: str,
        source: Path,
    ) -> None:
        """
        Repair an installed plugin from its source directory.
        """

        self._events.log.info(
            f"Repairing plugin '{qualified_name}'.",
        )

        plugin = self._repository.get_by_qualified_name(
            qualified_name,
        )

        repaired = self._installer.repair(
            plugin,
            source,
        )

        #
        # The installer is responsible for replacing the
        # installation. Refresh the runtime registry afterward.
        #

        self.refresh()

        #
        # `repair()` may return the updated Plugin metadata.
        # If it does not, the repository remains authoritative.
        #

        if repaired is not None:

            self._events.log.success(
                f"Plugin '{repaired.qualified_name}' " f"repaired successfully.",
            )

        else:

            self._events.log.success(
                f"Plugin '{qualified_name}' " f"repaired successfully.",
            )

    # ------------------------------------------------------------------
    # Enable / Disable
    # ------------------------------------------------------------------

    def enable(
        self,
        qualified_name: str,
    ) -> None:
        """
        Enable an installed plugin.
        """

        self._events.log.info(
            f"Enabling plugin '{qualified_name}'.",
        )

        plugin = self._repository.get_by_qualified_name(
            qualified_name,
        )

        assert plugin.id is not None

        self._repository.enable(
            plugin.id,
        )

        self.refresh()

        self._events.log.success(
            f"Plugin '{qualified_name}' enabled successfully.",
        )

    def disable(
        self,
        qualified_name: str,
    ) -> None:
        """
        Disable an installed plugin.
        """

        self._events.log.info(
            f"Disabling plugin '{qualified_name}'.",
        )

        plugin = self._repository.get_by_qualified_name(
            qualified_name,
        )

        assert plugin.id is not None

        self._repository.disable(
            plugin.id,
        )

        self.refresh()

        self._events.log.success(
            f"Plugin '{qualified_name}' disabled successfully.",
        )

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

    def finalize_installation(
        self,
        source: Path,
        destination: Path,
    ) -> None:
        """
        Finalize plugin paths after installation staging
        has been promoted to the permanent installation root.
        """

        self._repository.relocate_paths(
            source,
            destination,
        )

        self.refresh()

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

    def execute(
        self,
        context,
        qualified_name: str,
    ) -> None:
        """
        Execute a plugin.
        """

        self._runner.execute(
            context,
            qualified_name,
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

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def runner(
        self,
    ) -> PluginRunner:
        """
        Runtime plugin runner.
        """

        return self._runner

    # ------------------------------------------------------------------
    #  Man release notes
    # ------------------------------------------------------------------
    def documentation(
        self,
        qualified_name: str,
    ) -> str:
        """
        Return documentation for an installed plugin.
        """

        plugin = self.get(
            qualified_name,
        )

        documentation = (
            plugin.path / "MAN.md"
        )

        if not documentation.is_file():

            raise FileNotFoundError(
                f"Documentation not found for "
                f"plugin '{qualified_name}'."
            )

        return documentation.read_text(
            encoding="utf-8",
        )
