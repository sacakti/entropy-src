"""
ConfigMap and Secret update models.
"""

from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
from typing import Any


@dataclass(frozen=True)
class UpdateTarget:
    """
    Target ConfigMap or Secret.
    """

    kind: str
    name: str


@dataclass(frozen=True)
class UpdateOperation:
    """
    Single update operation.
    """

    action: str
    key: str
    value: Any = None
    format: str | None = None
    entries: dict[str, Any] | None = None


@dataclass(frozen=True)
class ConfigMapSecretUpdate:
    """
    ConfigMap/Secret update definition.
    """

    api_version: str
    kind: str
    target: UpdateTarget
    operations: list[UpdateOperation]

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UpdateError:
    """
    Error encountered while updating one resource.
    """

    kind: str
    name: str
    path: Path
    key: str | None
    message: str


@dataclass
class UpdateResult:
    """
    Result of updating one target resource.
    """

    kind: str
    name: str
    path: Path
    created: bool
    changes: list[dict[str, Any]]


@dataclass
class UpdateSummary:
    """
    Complete result of a ConfigMap/Secret update operation.
    """

    results: list[UpdateResult]
    errors: list[UpdateError]

    @property
    def failed(self) -> bool:
        """
        Return True when one or more resources failed.
        """

        return bool(
            self.errors,
        )

    @property
    def resources_processed(self) -> int:
        """
        Return the number of successfully processed resources
        plus failed resources.
        """

        return len(
            self.results,
        ) + len(
            {
                (
                    error.kind,
                    error.name,
                )
                for error in self.errors
            },
        )

    @property
    def resources_succeeded(self) -> int:
        """
        Return the number of successfully processed resources.
        """

        return len(
            self.results,
        )

    @property
    def resources_failed(self) -> int:
        """
        Return the number of resources with errors.
        """

        return len(
            {
                (
                    error.kind,
                    error.name,
                )
                for error in self.errors
            },
        )

    @property
    def changes_count(self) -> int:
        """
        Return the total number of successful changes.
        """

        return sum(
            len(
                result.changes,
            )
            for result in self.results
        )
