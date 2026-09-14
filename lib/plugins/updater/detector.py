"""
Plugin change detection.
"""

from __future__ import annotations

from packaging.version import Version

from lib.database.repositories.plugin_registry import PluginRepository
from lib.models.plugin import Plugin

from .model import PluginChange, PluginChangeType
from .source import PluginSource, PluginSourceDiscovery


class PluginChangeDetector:
    """
    Detects changes between installed plugins and plugins available
    from a plugin source.

    The installed plugin registry is authoritative for installed
    plugins. The source filesystem is authoritative for available
    plugin versions.
    """

    def __init__(
        self,
        repository: PluginRepository,
        source_discovery: PluginSourceDiscovery,
    ) -> None:

        self._repository = repository
        self._source_discovery = source_discovery

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def detect(
        self,
        source,
    ) -> list[PluginChange]:
        """
        Detect available plugin changes.

        Only new plugins, upgrades, and downgrades are returned.
        Plugins with the same installed and available version are
        ignored.

        Plugins installed in the database but missing from the source
        are also ignored. A missing source plugin must never imply
        automatic uninstallation.
        """

        available = self._source_discovery.discover(
            source,
        )

        installed = {plugin.qualified_name: plugin for plugin in self._repository.list()}

        changes: list[PluginChange] = []

        for plugin_source in available:

            plugin = installed.get(
                plugin_source.qualified_name,
            )

            change = self._compare(
                plugin_source,
                plugin,
            )

            if change is not None:

                changes.append(
                    change,
                )

        return sorted(
            changes,
            key=lambda change: (
                change.qualified_name,
                change.change_type.value,
            ),
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @staticmethod
    def _compare(
        source: PluginSource,
        installed: Plugin | None,
    ) -> PluginChange | None:
        """
        Compare an available plugin against its installed version.
        """

        if installed is None:

            return PluginChange(
                change_type=PluginChangeType.NEW,
                manifest=source.manifest,
                source=source.path,
            )

        available_version = Version(
            source.version,
        )

        installed_version = Version(
            installed.version,
        )

        if available_version == installed_version:

            return None

        if available_version > installed_version:

            change_type = PluginChangeType.UPGRADE

        else:

            change_type = PluginChangeType.DOWNGRADE

        return PluginChange(
            change_type=change_type,
            manifest=source.manifest,
            source=source.path,
            installed=installed,
        )
