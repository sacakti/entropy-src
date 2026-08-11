"""
Plugin manifest reader.
"""

from __future__ import annotations

from pathlib import Path

from core.constants import PLUGIN_MANIFEST
from core.context import EntropyContext
from lib.models.plugin import (
    EntropyRequirement,
    ExtensionRequirement,
    PluginManifest,
)

from .exceptions import PluginInvalidRequirementError, PluginManifestNotFoundError, PluginVersionError


class ManifestReader:
    """
    Reads plugin manifests.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.executor is not None

        self._executor = context.executor

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def read(
        self,
        directory: Path,
    ) -> PluginManifest:
        """
        Read a plugin manifest.
        """

        manifest = directory / PLUGIN_MANIFEST

        if not self._executor.exists(
            manifest,
        ):

            raise PluginManifestNotFoundError(
                manifest,
            )

        data = self._executor.read_json(
            manifest,
        )

        return PluginManifest(
            name=data["name"],
            namespace=data["namespace"],
            version=data["version"],
            module=data.get(
                "module",
                "plugin",
            ),
            display_name=data.get(
                "display_name",
            ),
            description=data.get(
                "description",
            ),
            author=data.get(
                "author",
            ),
            license=data.get(
                "license",
            ),
            entropy=self._read_entropy(
                data.get(
                    "entropy",
                ),
            ),
            extensions=self._read_extensions(
                data.get(
                    "dependencies",
                    [],
                ),
            ),
            tags=tuple(
                data.get(
                    "tags",
                    [],
                )
            ),
        )

    # ------------------------------------------------------------------
    # Entropy
    # ------------------------------------------------------------------

    @staticmethod
    def _read_entropy(
        value,
    ) -> EntropyRequirement | None:
        """
        Read the Entropy compatibility requirement.
        """

        if value is None:

            return None

        if isinstance(
            value,
            str,
        ):

            requirement = value.strip()

            if requirement.startswith(
                ">=",
            ):

                minimum = requirement[2:].strip()

                if not minimum:

                    raise PluginVersionError(
                        "Entropy minimum version cannot be empty.",
                    )

                return EntropyRequirement(
                    minimum=minimum,
                )

            raise PluginInvalidRequirementError(
                f"Unsupported Entropy requirement " f"'{requirement}'.",
            )

        if isinstance(
            value,
            dict,
        ):

            return EntropyRequirement(
                minimum=value["minimum"],
                maximum=value.get(
                    "maximum",
                ),
            )

        raise TypeError(
            "Plugin 'entropy' must be a string " "or an object.",
        )

    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------

    @staticmethod
    def _read_extensions(
        dependencies: list[dict],
    ) -> tuple[ExtensionRequirement, ...]:
        """
        Read plugin extension dependencies.
        """

        return tuple(
            ExtensionRequirement(
                name=item["name"],
                version=item.get(
                    "version",
                ),
            )
            for item in dependencies
        )
