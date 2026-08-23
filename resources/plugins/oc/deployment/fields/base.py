"""Deployment field handler base protocol."""

from __future__ import annotations

from typing import Any, Protocol

from ..model import DeploymentUpdateOperation


class DeploymentFieldHandler(Protocol):
    """Protocol implemented by Deployment field handlers."""

    def apply(
        self,
        document: dict[str, Any],
        operation: DeploymentUpdateOperation,
        *,
        target_image: str | None = None,
    ) -> dict[str, Any]: ...
