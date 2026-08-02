"""
Plugin metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PluginMetadata:
    """
    Immutable plugin metadata.
    """

    #
    # Identity
    #

    name: str

    namespace: str

    version: str

    #
    # Discovery
    #

    package: str

    module: str

    #
    # Presentation
    #

    display_name: str | None = None

    description: str | None = None

    author: str | None = None

    #
    # Capabilities
    #

    tags: tuple[str, ...] = field(
        default_factory=tuple,
    )

    # ------------------------------------------------------------------

    @property
    def qualified_name(self) -> str:
        """
        Namespace-qualified plugin name.

        Example:

            database.oracle
        """

        return f"{self.namespace}.{self.name}"
