"""Deployment image field handler."""

from __future__ import annotations

from typing import Any

from ..exceptions import DeploymentUpdateTargetError
from ..model import DeploymentUpdateOperation


class ImageFieldHandler:
    """Update a named container image."""

    def apply(
        self,
        document: dict[str, Any],
        operation: DeploymentUpdateOperation,
        *,
        target_image: str | None = None,
    ) -> dict[str, Any]:
        container_name = operation.container
        if not container_name:
            raise DeploymentUpdateTargetError(
                "Image operation requires 'container'.",
            )

        image = target_image if target_image is not None else operation.value
        if not isinstance(image, str) or not image.strip():
            raise DeploymentUpdateTargetError(
                f"Image operation for container '{container_name}' requires a target image.",
            )
        image = image.strip()

        containers = self._containers(document)
        container = self._find_container(containers, container_name)
        current = container.get("image")

        if current == image:
            return {
                "action": operation.action,
                "field": "image",
                "container": container_name,
                "status": "unchanged",
                "image": image,
            }

        if operation.action == "delete":
            raise DeploymentUpdateTargetError(
                "Image delete operation is not supported.",
            )

        container["image"] = image

        return {
            "action": operation.action,
            "field": "image",
            "container": container_name,
            "old_image": current,
            "new_image": image,
        }

    @staticmethod
    def _containers(document: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            containers = document["spec"]["template"]["spec"]["containers"]
        except (KeyError, TypeError) as exc:
            raise DeploymentUpdateTargetError(
                "Deployment does not contain spec.template.spec.containers.",
            ) from exc

        if not isinstance(containers, list):
            raise DeploymentUpdateTargetError(
                "Deployment containers must be an array.",
            )
        return [container for container in containers if isinstance(container, dict)]

    @staticmethod
    def _find_container(
        containers: list[dict[str, Any]],
        name: str,
    ) -> dict[str, Any]:
        for container in containers:
            if container.get("name") == name:
                return container
        raise DeploymentUpdateTargetError(
            f"Container '{name}' not found in Deployment.",
        )
