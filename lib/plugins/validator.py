"""
Plugin manifest validator.
"""

from __future__ import annotations

from packaging.version import InvalidVersion, Version

from lib.models.plugin import PluginManifest

from .exceptions import PluginValidationError


class ManifestValidator:
    """
    Validates plugin manifests.
    """

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def validate(
        self,
        manifest: PluginManifest,
    ) -> None:
        """
        Validate a plugin manifest.
        """

        self._validate_identity(
            manifest,
        )

        self._validate_version(
            manifest,
        )

        self._validate_extensions(
            manifest,
        )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def _validate_identity(
        self,
        manifest: PluginManifest,
    ) -> None:

        if not manifest.namespace.strip():

            raise PluginValidationError(
                "Plugin namespace cannot be empty.",
            )

        if not manifest.name.strip():

            raise PluginValidationError(
                "Plugin name cannot be empty.",
            )

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------

    def _validate_version(
        self,
        manifest: PluginManifest,
    ) -> None:

        try:

            Version(
                manifest.version,
            )

        except InvalidVersion as exc:

            raise PluginValidationError(
                f"Invalid plugin version '{manifest.version}'.",
            ) from exc

    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------

    def _validate_extensions(
        self,
        manifest: PluginManifest,
    ) -> None:

        seen: set[str] = set()

        for extension in manifest.extensions:

            if not extension.name.strip():

                raise PluginValidationError(
                    "Extension name cannot be empty.",
                )

            if extension.name in seen:

                raise PluginValidationError(
                    f"Duplicate extension '{extension.name}'.",
                )

            seen.add(
                extension.name,
            )
