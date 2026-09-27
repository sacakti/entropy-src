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
    """Build a Deployment update definition from release context."""

    if not isinstance(resource, dict):
        raise DeploymentUpdateDefinitionError(
            "Deployment context resource must be an object.",
        )

    name = resource.get("name")

    if not isinstance(name, str) or not name.strip():
        raise DeploymentUpdateDefinitionError(
            "Deployment context resource requires 'name'.",
        )

    # Explicit DeploymentUpdate operations.
    source_operations = resource.get("operations")

    if source_operations is not None:
        if not isinstance(source_operations, list):
            raise DeploymentUpdateDefinitionError(
                "Deployment context resource 'operations' "
                "must be an array.",
            )

        if not source_operations:
            raise DeploymentUpdateDefinitionError(
                "Deployment context resource 'operations' "
                "must not be empty.",
            )

        operations = [
            _build_operation(item)
            for item in source_operations
        ]

        return DeploymentUpdate(
            api_version="entropy/v1",
            kind="DeploymentUpdate",
            target=DeploymentUpdateTarget(
                kind="Deployment",
                name=name.strip(),
            ),
            operations=operations,
        )

    # Backward-compatible image context.
    for key in ("container", "target_image"):
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
            name=name.strip(),
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


def _build_operation(value: Any) -> DeploymentUpdateOperation:
    """Convert one context operation into a Deployment operation."""

    if not isinstance(value, dict):
        raise DeploymentUpdateDefinitionError(
            "Deployment context operation must be an object.",
        )

    action = value.get("action")
    field = value.get("field")

    if not isinstance(action, str) or not action.strip():
        raise DeploymentUpdateDefinitionError(
            "Deployment context operation requires 'action'.",
        )

    if not isinstance(field, str) or not field.strip():
        raise DeploymentUpdateDefinitionError(
            "Deployment context operation requires 'field'.",
        )

    container = value.get("container")

    if container is not None:
        if not isinstance(container, str) or not container.strip():
            raise DeploymentUpdateDefinitionError(
                "Deployment context operation 'container' "
                "must be a non-empty string when provided.",
            )

        container = container.strip()

    return DeploymentUpdateOperation(
        action=action.strip().lower(),
        field=field.strip().lower(),
        container=container,
        value=value.get("value"),
    )
