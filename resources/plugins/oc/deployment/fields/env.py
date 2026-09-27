"""Deployment environment variable field handler."""

from __future__ import annotations

from typing import Any

from ..exceptions import DeploymentUpdateTargetError
from ..model import DeploymentUpdateOperation


class EnvFieldHandler:
    """Update container environment variables."""

    def apply(
        self,
        document: dict[str, Any],
        operation: DeploymentUpdateOperation,
    ) -> dict[str, Any]:
        container_name = operation.container

        if not container_name:
            raise DeploymentUpdateTargetError(
                "Env operation requires 'container'.",
            )

        env = operation.value

        if not isinstance(env, dict):
            raise DeploymentUpdateTargetError(
                "Env operation requires an object 'value'.",
            )

        env_name = env.get("name")

        if not isinstance(env_name, str) or not env_name.strip():
            raise DeploymentUpdateTargetError(
                "Env operation requires a non-empty "
                "'value.name'.",
            )

        env_name = env_name.strip()

        containers = self._containers(document)
        container = self._find_container(
            containers,
            container_name,
        )

        environment = self._environment(container)

        existing_index = self._find_environment(
            environment,
            env_name,
        )

        if operation.action == "add":
            if existing_index is not None:
                raise DeploymentUpdateTargetError(
                    f"Environment variable '{env_name}' already "
                    f"exists in container '{container_name}'.",
                )

            environment.append(dict(env))

            return {
                "action": operation.action,
                "field": "env",
                "container": container_name,
                "name": env_name,
                "status": "added",
            }

        if operation.action == "update":
            if existing_index is None:
                raise DeploymentUpdateTargetError(
                    f"Environment variable '{env_name}' not found "
                    f"in container '{container_name}'.",
                )

            current = environment[existing_index]

            if current == env:
                return {
                    "action": operation.action,
                    "field": "env",
                    "container": container_name,
                    "name": env_name,
                    "status": "unchanged",
                }

            environment[existing_index] = dict(env)

            return {
                "action": operation.action,
                "field": "env",
                "container": container_name,
                "name": env_name,
                "status": "updated",
            }

        if operation.action == "delete":
            if existing_index is None:
                raise DeploymentUpdateTargetError(
                    f"Environment variable '{env_name}' not found "
                    f"in container '{container_name}'.",
                )

            del environment[existing_index]

            return {
                "action": operation.action,
                "field": "env",
                "container": container_name,
                "name": env_name,
                "status": "deleted",
            }

        raise DeploymentUpdateTargetError(
            f"Unsupported env operation '{operation.action}'.",
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
    def _environment(
        container: dict[str, Any],
    ) -> list[dict[str, Any]]:
        environment = container.get("env")

        if environment is None:
            environment = []
            container["env"] = environment

        if not isinstance(environment, list):
            raise DeploymentUpdateTargetError(
                "Container env must be an array.",
            )

        for item in environment:
            if not isinstance(item, dict):
                raise DeploymentUpdateTargetError(
                    "Container env must contain objects.",
                )

        return environment

    @staticmethod
    def _find_environment(
        environment: list[dict[str, Any]],
        name: str,
    ) -> int | None:
        for index, item in enumerate(environment):
            if item.get("name") == name:
                return index

        return None
