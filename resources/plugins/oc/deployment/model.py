"""Deployment update models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeploymentUpdateTarget:
    """Deployment resource target."""

    kind: str
    name: str


@dataclass(frozen=True)
class DeploymentUpdateOperation:
    """One Deployment field operation."""

    action: str
    field: str
    container: str | None = None
    value: Any = None


@dataclass(frozen=True)
class DeploymentUpdate:
    """Complete Deployment update definition."""

    api_version: str
    kind: str
    target: DeploymentUpdateTarget
    operations: list[DeploymentUpdateOperation]
