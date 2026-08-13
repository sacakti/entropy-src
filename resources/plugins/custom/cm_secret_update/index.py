"""
ConfigMap/Secret target resource index.
"""

from __future__ import annotations

from .target_loader import TargetResource


class ConfigMapSecretTargetIndex:
    """
    Index ConfigMap and Secret resources by kind and name.
    """

    def __init__(
        self,
        resources: list[TargetResource],
    ) -> None:

        self._resources: dict[
            tuple[str, str],
            TargetResource,
        ] = {
            (
                resource.kind,
                resource.name,
            ): resource
            for resource in resources
        }

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        kind: str,
        name: str,
    ) -> TargetResource | None:
        """
        Return a resource by kind and metadata.name.
        """

        return self._resources.get(
            (
                kind,
                name,
            ),
        )

    # ------------------------------------------------------------------
    # Contains
    # ------------------------------------------------------------------

    def contains(
        self,
        kind: str,
        name: str,
    ) -> bool:
        """
        Return whether a resource exists.
        """

        return (
            kind,
            name,
        ) in self._resources

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    def resources(
        self,
    ) -> list[TargetResource]:
        """
        Return all indexed resources.
        """

        return list(
            self._resources.values(),
        )
