"""
Extension manifest loader.
"""

from __future__ import annotations
from pathlib import Path

from lib.models.extensions import ExtensionManifest


class ExtensionLoader:
    """
    Creates extension manifests from various sources.

    This class is responsible only for converting
    input into an ExtensionManifest.
    """

    # ------------------------------------------------------------------
    # Name
    # ------------------------------------------------------------------

    def from_name(
        self,
        name: str,
        version: str | None = None,
    ) -> ExtensionManifest:
        """
        Create a manifest from a package name.
        """

        return ExtensionManifest(
            name=name,
            version=version,
        )

    # ------------------------------------------------------------------
    # Plugin Dependency
    # ------------------------------------------------------------------

    def from_dependency(
        self,
        dependency: dict,
    ) -> ExtensionManifest:
        """
        Create a manifest from a plugin dependency.

        Example
        -------
        {
            "name": "sqlparse",
            "version": "0.5.3"
        }
        """

        return ExtensionManifest(
            name=dependency["name"],
            version=dependency.get("version"),
        )

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def from_json(
        self,
        data: dict,
    ) -> ExtensionManifest:
        """
        Create a manifest from a JSON object.
        """

        return ExtensionManifest(
            name=data["name"],
            version=data.get("version"),
            source=data.get("source"),
            checksum=data.get("checksum"),
            installer=data.get(
                "installer",
                "offline",
            ),
        )

    def from_file(
        self,
        path: Path,
    ) -> ExtensionManifest:
        """
        Load a manifest from a JSON file.
        """

        raise NotImplementedError()


    def from_wheel(
        self,
        wheel: Path,
    ) -> ExtensionManifest:
        """
        Create a manifest by inspecting a wheel file.
        """

        raise NotImplementedError()
