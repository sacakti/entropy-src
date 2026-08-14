from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


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

    extensions: tuple[ExtensionRequirement, ...] = field(
        default_factory=tuple,
    )

    #
    # Classification
    #

    tags: tuple[str, ...] = field(
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

        return f"{self.namespace}." f"{self.name}"


@dataclass
class PluginResult:
    """
    Standard result returned by a plugin execution.

    The result is intentionally independent from workflow
    presentation. A workflow may suppress rendering of the
    result while the runtime still retains it.
    """

    success: bool = True
    changed: bool = False
    outputs: dict[str, Any] = field(
        default_factory=dict,
    )
    changes: list[dict[str, Any]] = field(
        default_factory=list,
    )
    errors: list[dict[str, Any]] = field(
        default_factory=list,
    )
    warnings: list[str] = field(
        default_factory=list,
    )
    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    def to_dict(self) -> dict[str, Any]:
        """
        Return the result as JSON-compatible data.
        """

        return asdict(self)
