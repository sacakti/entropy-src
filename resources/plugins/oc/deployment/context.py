"""Helpers for converting release-context deployment output."""

from __future__ import annotations

from typing import Any

from .exceptions import DeploymentUpdateDefinitionError
from .model import (
    DeploymentUpdate,
    DeploymentUpdateOperation,
    DeploymentUpdateTarget,
)


def build_context_definition(resource: Any) -> DeploymentUpdate:
    """Build an image update definition from BuildReleaseContext output."""
    if not isinstance(resource, dict):
        raise DeploymentUpdateDefinitionError(
            "Deployment context resource must be an object.",
        )

    for key in ("name", "container", "target_image"):
        value = resource.get(key)
        if not isinstance(value, str) or not value.strip():
            raise DeploymentUpdateDefinitionError(
                f"Deployment context resource requires '{key}'.",
            )

    return DeploymentUpdate(
        api_version="entropy/v1",
        kind="DeploymentUpdate",
        target=DeploymentUpdateTarget(
            kind="Deployment",
            name=resource["name"].strip(),
        ),
        operations=[
            DeploymentUpdateOperation(
                action="update",
                field="image",
                container=resource["container"].strip(),
                value=resource["target_image"].strip(),
            ),
        ],
    )
