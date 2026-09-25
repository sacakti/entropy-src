"""
Plugin manifest validator.
"""

from __future__ import annotations

from packaging.version import InvalidVersion, Version
from packaging.specifiers import InvalidSpecifier, SpecifierSet

from lib.models.plugin import PluginManifest
from .exceptions import PluginValidationError

class ManifestValidator:
    """
    Validates plugin manifests.
    """

    def __init__(
        self,
        entropy_version: str,
    ) -> None:

        self._entropy_version = Version(
            entropy_version,
        )

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

        self._validate_entropy(
            manifest,
        )

        self._validate_required_plugins(
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

    # ------------------------------------------------------------------
    # Required Entropy
    # ------------------------------------------------------------------

    def _validate_entropy(
        self,
        manifest: PluginManifest,
    ) -> None:

        requirement = manifest.entropy

        if requirement is None:
            return

        minimum = Version(
            requirement.minimum,
        )

        if self._entropy_version < minimum:

            raise PluginValidationError(
                f"Plugin '{manifest.qualified_name}' requires "
                f"Entropy >= {requirement.minimum}, "
                f"but the current version is "
                f"{self._entropy_version}.",
            )

        if requirement.maximum is not None:

            maximum = Version(
                requirement.maximum,
            )

            if self._entropy_version > maximum:

                raise PluginValidationError(
                    f"Plugin '{manifest.qualified_name}' requires "
                    f"Entropy <= {requirement.maximum}, "
                    f"but the current version is "
                    f"{self._entropy_version}.",
                )

    # ------------------------------------------------------------------
    # Required Plugins
    # ------------------------------------------------------------------

    def _validate_required_plugins(
        self,
        manifest: PluginManifest,
    ) -> None:

        seen: set[str] = set()

        for requirement in manifest.required_plugins:

            name = requirement.name.strip()

            if not name:

                raise PluginValidationError(
                    "Required plugin name cannot be empty.",
                )

            if name in seen:

                raise PluginValidationError(
                    f"Duplicate required plugin '{name}'.",
                )

            seen.add(
                name,
            )

            if requirement.version is not None:

                try:

                    SpecifierSet(
                        requirement.version,
                    )

                except InvalidSpecifier as exc:

                    raise PluginValidationError(
                        f"Invalid version requirement "
                        f"'{requirement.version}' "
                        f"for plugin '{name}'.",
                    ) from exc

            import_seen: set[str] = set()

            for imported in requirement.imports:

                reference = imported.reference

                if reference in import_seen:

                    raise PluginValidationError(
                        f"Duplicate import '{reference}' "
                        f"for plugin '{name}'.",
                    )

                import_seen.add(
                    reference,
                )

                if not imported.module.strip():

                    raise PluginValidationError(
                        f"Import module cannot be empty "
                        f"for plugin '{name}'.",
                    )

                if not imported.symbol.strip():

                    raise PluginValidationError(
                        f"Import symbol cannot be empty "
                        f"for plugin '{name}'.",
                    )
