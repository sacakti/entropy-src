"""
Plugin source discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lib.models.plugin import PluginManifest

from ..exceptions import PluginValueError
from ..manifest import ManifestReader
from ..validator import ManifestValidator


@dataclass(frozen=True)
class PluginSource:
    """
    Discovered plugin source.

    Represents a plugin package available in a plugin source
    directory. The source filesystem is read-only to this component.
    """

    manifest: PluginManifest
    path: Path

    @property
    def qualified_name(self) -> str:
        """Return the fully-qualified plugin name."""
        return self.manifest.qualified_name

    @property
    def version(self) -> str:
        """Return the available plugin version."""
        return self.manifest.version


class PluginSourceDiscovery:
    """
    Discovers plugins available from a source directory.

    This component only reads plugin manifests. It does not install,
    update, remove, or modify plugins.
    """

    def __init__(
        self,
        reader: ManifestReader,
        validator: ManifestValidator,
    ) -> None:
        self._reader = reader
        self._validator = validator

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
        directory: Path,
    ) -> list[PluginSource]:
        """
        Discover plugin packages below ``directory``.

        Plugin packages are identified by the presence of
        ``plugin.json``. Discovery is recursive so both namespace/name
        layouts and deeper source layouts are supported.
        """

        source = directory.expanduser().resolve()

        if not source.exists():
            raise PluginValueError(
                f"Plugin source directory not found: {source}",
            )

        if not source.is_dir():
            raise PluginValueError(
                f"Plugin source is not a directory: {source}",
            )

        discovered: list[PluginSource] = []
        seen: set[str] = set()

        for manifest_file in sorted(source.rglob("plugin.json")):
            plugin_directory = manifest_file.parent

            manifest = self._reader.read(
                plugin_directory,
            )

            self._validator.validate(
                manifest,
            )

            if manifest.qualified_name in seen:
                raise PluginValueError(
                    f"Duplicate plugin '{manifest.qualified_name}' "
                    f"found in source '{source}'.",
                )

            seen.add(
                manifest.qualified_name,
            )

            discovered.append(
                PluginSource(
                    manifest=manifest,
                    path=plugin_directory.resolve(),
                ),
            )

        return sorted(
            discovered,
            key=lambda plugin: plugin.qualified_name,
        )
