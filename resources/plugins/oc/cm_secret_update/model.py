"""
ConfigMap and Secret update models.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class SourceType(
    Enum,
):
    """
    Type of ConfigMap/Secret source definition.
    """

    UPDATE = "update"
    RESOURCE = "resource"


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
    Single ConfigMap/Secret update operation.
    """

    action: str
    key: str
    value: Any = None
    format: str | None = None
    entries: dict[str, Any] | list[str] | None = None


@dataclass(frozen=True)
class ConfigMapSecretUpdate:
    """
    ConfigMap/Secret update definition.
    """

    api_version: str
    kind: str
    target: UpdateTarget
    operations: list[UpdateOperation]


@dataclass(frozen=True)
class ConfigMapSecretResource:
    """
    Native ConfigMap or Secret resource.

    A native resource represents the complete resource supplied
    by the release. When the target already exists:

    - replace=False means merge the supplied data into the target.
    - replace=True means replace the complete target resource.
    """

    api_version: str
    kind: str
    name: str
    document: dict[str, Any]


@dataclass(frozen=True)
class ConfigMapSecretSource:
    """
    Source ConfigMap/Secret definition.

    A source is either:

    - an entropy/v1 ConfigMapSecretUpdate definition, or
    - a native ConfigMap/Secret resource.
    """

    source_type: SourceType
    path: Path
    update: ConfigMapSecretUpdate | None = None
    resource: ConfigMapSecretResource | None = None

    def __post_init__(self) -> None:
        """
        Validate source payload consistency.
        """

        if self.source_type == SourceType.UPDATE:

            if self.update is None:
                raise ValueError(
                    "Update source requires an update definition.",
                )

            if self.resource is not None:
                raise ValueError(
                    "Update source cannot contain a native resource.",
                )

            return

        if self.source_type == SourceType.RESOURCE:

            if self.resource is None:
                raise ValueError(
                    "Resource source requires a native resource.",
                )

            if self.update is not None:
                raise ValueError(
                    "Resource source cannot contain an update definition.",
                )

            return

        raise ValueError(
            f"Unsupported source type '{self.source_type}'.",
        )

    @property
    def kind(self) -> str:
        """
        Return the source resource kind.
        """

        if self.source_type == SourceType.UPDATE:

            assert self.update is not None

            return self.update.target.kind

        assert self.resource is not None

        return self.resource.kind

    @property
    def name(self) -> str:
        """
        Return the source resource name.
        """

        if self.source_type == SourceType.UPDATE:

            assert self.update is not None

            return self.update.target.name

        assert self.resource is not None

        return self.resource.name


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
