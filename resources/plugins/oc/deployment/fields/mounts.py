"""Deployment volume mount field handler."""

from __future__ import annotations

from typing import Any

from ..exceptions import DeploymentUpdateTargetError
from ..model import DeploymentUpdateOperation


class MountsFieldHandler:
    """Update container volume mounts."""

    def apply(
        self,
        document: dict[str, Any],
        operation: DeploymentUpdateOperation,
    ) -> dict[str, Any]:
        container_name = operation.container

        if not container_name:
            raise DeploymentUpdateTargetError(
                "Mounts operation requires 'container'.",
            )

        mount = operation.value

        if not isinstance(mount, dict):
            raise DeploymentUpdateTargetError(
                "Mounts operation requires an object 'value'.",
            )

        mount_name = mount.get("name")

        if not isinstance(mount_name, str) or not mount_name.strip():
            raise DeploymentUpdateTargetError(
                "Mounts operation requires a non-empty "
                "'value.name'.",
            )

        mount_name = mount_name.strip()

        containers = self._containers(document)
        container = self._find_container(
            containers,
            container_name,
        )

        mounts = self._mounts(container)

        existing_index = self._find_mount(
            mounts,
            mount_name,
        )

        if operation.action == "add":
            if existing_index is not None:
                raise DeploymentUpdateTargetError(
                    f"Volume mount '{mount_name}' already exists "
                    f"in container '{container_name}'.",
                )

            mounts.append(dict(mount))

            return {
                "action": operation.action,
                "field": "mounts",
                "container": container_name,
                "name": mount_name,
                "status": "added",
            }

        if operation.action == "update":
            if existing_index is None:
                raise DeploymentUpdateTargetError(
                    f"Volume mount '{mount_name}' not found "
                    f"in container '{container_name}'.",
                )

            current = mounts[existing_index]

            if current == mount:
                return {
                    "action": operation.action,
                    "field": "mounts",
                    "container": container_name,
                    "name": mount_name,
                    "status": "unchanged",
                }

            mounts[existing_index] = dict(mount)

            return {
                "action": operation.action,
                "field": "mounts",
                "container": container_name,
                "name": mount_name,
                "status": "updated",
            }

        if operation.action == "delete":
            if existing_index is None:
                raise DeploymentUpdateTargetError(
                    f"Volume mount '{mount_name}' not found "
                    f"in container '{container_name}'.",
                )

            del mounts[existing_index]

            return {
                "action": operation.action,
                "field": "mounts",
                "container": container_name,
                "name": mount_name,
                "status": "deleted",
            }

        raise DeploymentUpdateTargetError(
            f"Unsupported mounts operation '{operation.action}'.",
        )

    @staticmethod
    def _containers(
        document: dict[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            containers = (
                document["spec"]
                ["template"]
                ["spec"]
                ["containers"]
            )
        except (KeyError, TypeError) as exc:
            raise DeploymentUpdateTargetError(
                "Deployment does not contain "
                "spec.template.spec.containers.",
            ) from exc

        if not isinstance(containers, list):
            raise DeploymentUpdateTargetError(
                "Deployment containers must be an array.",
            )

        return [
            container
            for container in containers
            if isinstance(container, dict)
        ]

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

    @staticmethod
    def _mounts(
        container: dict[str, Any],
    ) -> list[dict[str, Any]]:
        mounts = container.get("volumeMounts")

        if mounts is None:
            mounts = []
            container["volumeMounts"] = mounts

        if not isinstance(mounts, list):
            raise DeploymentUpdateTargetError(
                "Container volumeMounts must be an array.",
            )

        for mount in mounts:
            if not isinstance(mount, dict):
                raise DeploymentUpdateTargetError(
                    "Container volumeMounts must contain objects.",
                )

        return mounts

    @staticmethod
    def _find_mount(
        mounts: list[dict[str, Any]],
        name: str,
    ) -> int | None:
        for index, mount in enumerate(mounts):
            if mount.get("name") == name:
                return index

        return None
