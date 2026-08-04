"""
Plugin manifest reader.
"""

from __future__ import annotations

from pathlib import Path

from core.context import EntropyContext

from lib.models.plugin import (
    EntropyRequirement,
    ExtensionRequirement,
    PluginManifest,
)

from .exceptions import PluginManifestNotFoundError


class ManifestReader:
    """
    Reads plugin manifests.
    """

    FILE = "plugin.json"

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

        manifest = (
            directory /
            self.FILE
        )

        if not self._executor.exists(
            manifest,
        ):

            raise PluginManifestNotFoundError(
                manifest,
            )

        data = self._executor.read_json(
            manifest,
        )

        entropy = data.get(
            "entropy",
        )

        return PluginManifest(
            name=data["name"],
            namespace=data["namespace"],
            version=data["version"],
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
            entropy=(
                EntropyRequirement(
                    minimum=entropy["minimum"],
                    maximum=entropy.get(
                        "maximum",
                    ),
                )
                if entropy
                else None
            ),
            extensions=tuple(
                ExtensionRequirement(
                    name=item["name"],
                    version=item.get(
                        "version",
                    ),
                )
                for item in data.get(
                    "extensions",
                    [],
                )
            ),
            tags=tuple(
                data.get(
                    "tags",
                    [],
                )
            ),
        )
