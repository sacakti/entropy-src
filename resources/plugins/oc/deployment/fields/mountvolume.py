"""Deployment volume field handler."""

from __future__ import annotations

from typing import Any

from ..exceptions import DeploymentUpdateTargetError
from ..model import DeploymentUpdateOperation


class MountVolumeFieldHandler:
    """Update Deployment volumes."""

    def apply(
        self,
        document: dict[str, Any],
        operation: DeploymentUpdateOperation,
    ) -> dict[str, Any]:
        if operation.container is not None:
            raise DeploymentUpdateTargetError(
                "Mountvolume operation does not support 'container'.",
            )

        volume = operation.value

        if not isinstance(volume, dict):
            raise DeploymentUpdateTargetError(
                "Mountvolume operation requires an object 'value'.",
            )

        volume_name = volume.get("name")

        if not isinstance(volume_name, str) or not volume_name.strip():
            raise DeploymentUpdateTargetError(
                "Mountvolume operation requires a non-empty "
                "'value.name'.",
            )

        volume_name = volume_name.strip()

        volumes = self._volumes(document)

        existing_index = self._find_volume(
            volumes,
            volume_name,
        )

        if operation.action == "add":
            if existing_index is not None:
                raise DeploymentUpdateTargetError(
                    f"Volume '{volume_name}' already exists in Deployment.",
                )

            volumes.append(dict(volume))

            return {
                "action": operation.action,
                "field": "mountvolume",
                "name": volume_name,
                "status": "added",
            }

        if operation.action == "update":
            if existing_index is None:
                raise DeploymentUpdateTargetError(
                    f"Volume '{volume_name}' not found in Deployment.",
                )

            current = volumes[existing_index]

            if current == volume:
                return {
                    "action": operation.action,
                    "field": "mountvolume",
                    "name": volume_name,
                    "status": "unchanged",
                }

            volumes[existing_index] = dict(volume)

            return {
                "action": operation.action,
                "field": "mountvolume",
                "name": volume_name,
                "status": "updated",
            }

        if operation.action == "delete":
            if existing_index is None:
                raise DeploymentUpdateTargetError(
                    f"Volume '{volume_name}' not found in Deployment.",
                )

            del volumes[existing_index]

            return {
                "action": operation.action,
                "field": "mountvolume",
                "name": volume_name,
                "status": "deleted",
            }

        raise DeploymentUpdateTargetError(
            f"Unsupported mountvolume operation '{operation.action}'.",
        )

    @staticmethod
    def _volumes(
        document: dict[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            spec = document["spec"]["template"]["spec"]
        except (KeyError, TypeError) as exc:
            raise DeploymentUpdateTargetError(
                "Deployment does not contain "
                "spec.template.spec.",
            ) from exc

        if not isinstance(spec, dict):
            raise DeploymentUpdateTargetError(
                "Deployment spec.template.spec must be an object.",
            )

        volumes = spec.get("volumes")

        if volumes is None:
            volumes = []
            spec["volumes"] = volumes

        if not isinstance(volumes, list):
            raise DeploymentUpdateTargetError(
                "Deployment volumes must be an array.",
            )

        for volume in volumes:
            if not isinstance(volume, dict):
                raise DeploymentUpdateTargetError(
                    "Deployment volumes must contain objects.",
                )

        return volumes

    @staticmethod
    def _find_volume(
        volumes: list[dict[str, Any]],
        name: str,
    ) -> int | None:
        for index, volume in enumerate(volumes):
            if volume.get("name") == name:
                return index

        return None
