from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class Plugin:

    namespace: str

    name: str

    version: str

    path: Path

    id: int | None = None

    enabled: bool = True

    installed_at: datetime | None = None

    @property
    def qualified_name(self) -> str:

        return f"{self.namespace}.{self.name}"

    @property
    def module_file(
        self,
    ) -> Path:
        """
        Plugin implementation.
        """

        return self.path / "plugin.py"


# ------------------------------------------------------------------
# Entropy Requirement
# ------------------------------------------------------------------


@dataclass(frozen=True)
class EntropyRequirement:
    """
    Supported Entropy versions.
    """

    minimum: str

    maximum: str | None = None


# ------------------------------------------------------------------
# Extension Requirement
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ExtensionRequirement:
    """
    Required extension dependency.
    """

    name: str

    version: str | None = None


# ------------------------------------------------------------------
# Plugin Manifest
# ------------------------------------------------------------------


@dataclass(frozen=True)
class PluginManifest:
    """
    Representation of plugin.json.
    """

    #
    # Identity
    #

    namespace: str

    name: str

    version: str

    module: str = "plugin"

    #
    # Presentation
    #

    display_name: str | None = None

    description: str | None = None

    author: str | None = None

    license: str | None = None

    #
    # Compatibility
    #

    entropy: EntropyRequirement | None = None

    #
    # Dependencies
    #

    extensions: tuple[
        ExtensionRequirement,
        ...
    ] = field(
        default_factory=tuple,
    )

    #
    # Classification
    #

    tags: tuple[
        str,
        ...
    ] = field(
        default_factory=tuple,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def qualified_name(
        self,
    ) -> str:
        """
        Return the fully-qualified plugin name.
        """

        return (
            f"{self.namespace}."
            f"{self.name}"
        )
