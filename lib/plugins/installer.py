"""
Plugin installer.
"""

from __future__ import annotations

from pathlib import Path

from core.context import EntropyContext
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
        # Rollback plugin migrations.
        #

        migrations = (
            plugin.path /
            "migrations"
        )

        if migrations.exists():

            self._migrations.rollback(
                migrations,
            )

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

        self._migrations.run(
            migrations,
        )

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
