"""
Plugin update models.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from lib.models.plugin import Plugin, PluginManifest


class PluginChangeType(str, Enum):
    """
    Type of change detected between an installed plugin
    and an available plugin source.
    """

    NEW = "new"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"


@dataclass(frozen=True)
class PluginChange:
    """
    Represents a detected plugin version change.
    """

    change_type: PluginChangeType

    manifest: PluginManifest

    source: Path

    installed: Plugin | None = None

    @property
    def qualified_name(self) -> str:
        """
        Return the plugin qualified name.
        """

        return self.manifest.qualified_name

    @property
    def available_version(self) -> str:
        """
        Return the available plugin version.
        """

        return self.manifest.version

    @property
    def installed_version(self) -> str | None:
        """
        Return the installed version.

        Returns None for newly discovered plugins.
        """

        if self.installed is None:
            return None

        return self.installed.version

    @property
    def is_new(self) -> bool:
        """
        Return True if this is a new plugin.
        """

        return self.change_type is PluginChangeType.NEW

    @property
    def is_upgrade(self) -> bool:
        """
        Return True if this is an upgrade.
        """

        return self.change_type is PluginChangeType.UPGRADE

    @property
    def is_downgrade(self) -> bool:
        """
        Return True if this is a downgrade.
        """

        return self.change_type is PluginChangeType.DOWNGRADE
