"""Deployment update engine."""

from __future__ import annotations

from typing import Any

from .exceptions import DeploymentUpdateTargetError
from .fields import FIELD_HANDLERS
from .model import DeploymentUpdate


class DeploymentUpdateEngine:
    """Apply Deployment update operations."""

    def __init__(self, field_handlers=None) -> None:
        self._handlers = field_handlers if field_handlers is not None else FIELD_HANDLERS

    def apply(
        self,
        document: dict[str, Any],
        definition: DeploymentUpdate,
        *,
        target_image: str | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_target(document, definition)
        changes: list[dict[str, Any]] = []

        for operation in definition.operations:
            handler = self._handlers.get(operation.field)
            if handler is None:
                raise DeploymentUpdateTargetError(
                    f"Unsupported Deployment field '{operation.field}'.",
                )

            handler_kwargs: dict[str, Any] = {}

            if operation.field == "image":
                handler_kwargs["target_image"] = target_image

            changes.append(
                handler.apply(
                    document,
                    operation,
                    **handler_kwargs,
                ),
            )
        return changes

    @staticmethod
    def _validate_target(
        document: dict[str, Any],
        definition: DeploymentUpdate,
    ) -> None:
        if document.get("kind") != definition.target.kind:
            raise DeploymentUpdateTargetError(
                f"Target document kind '{document.get('kind')}' does not match '{definition.target.kind}'.",
            )
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            raise DeploymentUpdateTargetError("Deployment must contain metadata.")
        if metadata.get("name") != definition.target.name:
            raise DeploymentUpdateTargetError(
                f"Target Deployment '{definition.target.name}' not found.",
            )
