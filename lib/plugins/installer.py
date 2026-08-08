"""
Plugin installer.
"""

from __future__ import annotations

from pathlib import Path

from core.context import EntropyContext
from core.exceptions import EntropyException
from lib.database.repositories.plugin_registry import PluginRepository
from lib.extensions.manager import ExtensionManager
from lib.migrations.manager import MigrationManager
from lib.models.plugin import Plugin, PluginManifest

from .manifest import ManifestReader
from .validator import ManifestValidator
from .exceptions import (
    PluginAlreadyInstalledError,
)


class PluginInstaller:
    """
    Installs Entropy plugins.
    """

    def __init__(
        self,
        context: EntropyContext,
        repository: PluginRepository,
        reader: ManifestReader,
        validator: ManifestValidator,
        extensions: ExtensionManager,
        migrations: MigrationManager,
    ) -> None:

        assert context.executor is not None
        assert context.paths is not None

        self._executor = context.executor
        self._paths = context.paths

        self._repository = repository

        self._reader = reader

        self._validator = validator

        self._extensions = extensions

        self._migrations = migrations

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

        manifest = self._reader.read(
            directory,
        )

        destination = (
            self._paths.plugins.directory /
            manifest.namespace /
            manifest.name
        )

        self._validator.validate(
            manifest,
        )

        exists = self._repository.exists(
            manifest.namespace,
            manifest.name,
        )

        if exists:

            if not reinstall:

                raise PluginAlreadyInstalledError(
                    manifest.qualified_name,
                )

            plugin = self._repository.get_by_name(
                manifest.namespace,
                manifest.name,
            )

            self.uninstall(
                plugin,
            )

        self._install_extensions(
            manifest,
        )

        self._executor.copy(
            directory,
            destination,
        )

        self._run_migrations(
            destination,
        )

        return self._register(
            manifest,
            destination.resolve(),
        )


    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def uninstall(
        self,
        plugin: Plugin,
    ) -> None:
        """
        Uninstall a plugin.
        """

        #
        # Remove plugin directory.
        #

        if plugin.path.exists():

            self._executor.remove(
                plugin.path,
            )

        #
        # Remove registration.
        #

        assert plugin.id is not None

        self._repository.delete(
            plugin.id,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _ensure_not_installed(
        self,
        manifest: PluginManifest,
    ) -> None:
        """
        Ensure the plugin is not already installed.
        """

        if self._repository.exists(
            manifest.namespace,
            manifest.name,
        ):

            raise PluginAlreadyInstalledError(
                manifest.qualified_name,
            )

    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------

    def _install_extensions(
        self,
        manifest: PluginManifest,
    ) -> None:
        """
        Install required extensions.
        """

        for requirement in manifest.extensions:

            if self._extensions.exists(
                requirement.name,
            ):

                continue

            #
            # Reuse Extension subsystem.
            #

            self._extensions.install(
                requirement,
            )

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    def _run_migrations(
        self,
        directory: Path,
    ) -> None:
        """
        Execute plugin migrations.
        """

        migrations = (
            directory /
            "migrations"
        )

        if not migrations.exists():

            return

        try:
            self._migrations.run(
                migrations,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register(
        self,
        manifest: PluginManifest,
        directory: Path,
    ) -> Plugin:
        """
        Register the plugin.
        """

        plugin = Plugin(
            namespace=manifest.namespace,
            name=manifest.name,
            version=manifest.version,
            path=directory,
        )

        return self._repository.create(
            plugin,
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(
        self,
        plugin: Plugin,
    ) -> None:
        """
        Verify an installed plugin.

        Raises an exception if the installation is incomplete
        or inconsistent.
        """

        if not plugin.path.exists():

            raise EntropyException(
                f"Plugin directory not found for "
                f"'{plugin.qualified_name}': {plugin.path}",
            )

        if not plugin.path.is_dir():

            raise EntropyException(
                f"Plugin path is not a directory for "
                f"'{plugin.qualified_name}': {plugin.path}",
            )

        manifest_file = (
            plugin.path /
            "plugin.json"
        )

        if not manifest_file.exists():

            raise EntropyException(
                f"Plugin manifest not found for "
                f"'{plugin.qualified_name}': {manifest_file}",
            )

        manifest = self._reader.read(
            plugin.path,
        )

        self._validator.validate(
            manifest,
        )

        if manifest.namespace != plugin.namespace:

            raise EntropyException(
                f"Plugin namespace mismatch for "
                f"'{plugin.qualified_name}'.",
            )

        if manifest.name != plugin.name:

            raise EntropyException(
                f"Plugin name mismatch for "
                f"'{plugin.qualified_name}'.",
            )

        if manifest.version != plugin.version:

            raise EntropyException(
                f"Plugin version mismatch for "
                f"'{plugin.qualified_name}'. "
                f"Registered: {plugin.version}, "
                f"Manifest: {manifest.version}.",
            )

        #
        # Required plugin files.
        #

        required = (
            "plugin.json",
            "plugin.py",
        )

        missing = [
            plugin.path / file
            for file in required
            if not (plugin.path / file).exists()
        ]

        if missing:

            files = "\n".join(
                f"- {path}"
                for path in missing
            )

            raise EntropyException(
                f"Plugin '{plugin.qualified_name}' "
                f"is incomplete. Missing files:\n"
                f"{files}",
            )

    # ------------------------------------------------------------------
    # Repair
    # ------------------------------------------------------------------

    def repair(
        self,
        plugin: Plugin,
        source: Path,
    ) -> Plugin:
        """
        Repair an installed plugin.

        The existing installation is removed and the plugin
        is installed again from the supplied source directory.
        """

        if not source.exists():

            raise EntropyException(
                f"Plugin source directory not found: {source}",
            )

        if not source.is_dir():

            raise EntropyException(
                f"Plugin source is not a directory: {source}",
            )

        manifest = self._reader.read(
            source,
        )

        self._validator.validate(
            manifest,
        )

        if (
            manifest.namespace != plugin.namespace
            or manifest.name != plugin.name
        ):

            raise EntropyException(
                f"Plugin source '{manifest.qualified_name}' "
                f"does not match installed plugin "
                f"'{plugin.qualified_name}'.",
            )

        self.uninstall(
            plugin,
        )

        return self.install(
            source,
        )
