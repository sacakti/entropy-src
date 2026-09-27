"""Deployment update definition validator."""

from __future__ import annotations

from typing import Any

from .exceptions import DeploymentUpdateDefinitionError
from .model import (
    DeploymentUpdate,
    DeploymentUpdateOperation,
    DeploymentUpdateTarget,
)


class DeploymentUpdateValidator:
    """Validate and convert Deployment update definitions."""

    API_VERSION = "entropy/v1"
    KIND = "DeploymentUpdate"
    TARGET_KIND = "Deployment"

    ACTIONS = {"add", "update", "delete"}

    FIELDS = {
        "image",
        "mounts",
        "mountvolume",
        "env",
    }

    CONTAINER_FIELDS = {
        "image",
        "mounts",
        "env",
    }

    OBJECT_FIELDS = {
        "mounts",
        "mountvolume",
        "env",
    }

    @classmethod
    def parse(cls, value: Any) -> DeploymentUpdate:
        if not isinstance(value, dict):
            raise DeploymentUpdateDefinitionError(
                "Deployment update definition must be an object.",
            )

        if value.get("apiVersion") != cls.API_VERSION:
            raise DeploymentUpdateDefinitionError(
                f"Unsupported apiVersion '{value.get('apiVersion')}'. "
                f"Expected '{cls.API_VERSION}'.",
            )

        if value.get("kind") != cls.KIND:
            raise DeploymentUpdateDefinitionError(
                f"Invalid update definition kind '{value.get('kind')}'. "
                f"Expected '{cls.KIND}'.",
            )

        target = value.get("target")
        if not isinstance(target, dict):
            raise DeploymentUpdateDefinitionError(
                "'target' must be an object.",
            )

        target_kind = target.get("kind")
        if target_kind != cls.TARGET_KIND:
            raise DeploymentUpdateDefinitionError(
                f"Unsupported target kind '{target_kind}'. "
                f"Expected '{cls.TARGET_KIND}'.",
            )

        name = target.get("name")
        if not isinstance(name, str) or not name.strip():
            raise DeploymentUpdateDefinitionError(
                "Target 'name' must be a non-empty string.",
            )

        operations = value.get("operations")
        if not isinstance(operations, list) or not operations:
            raise DeploymentUpdateDefinitionError(
                "'operations' must be a non-empty array.",
            )

        parsed = [
            cls._operation(item)
            for item in operations
        ]

        return DeploymentUpdate(
            api_version=cls.API_VERSION,
            kind=cls.KIND,
            target=DeploymentUpdateTarget(
                kind=target_kind,
                name=name.strip(),
            ),
            operations=parsed,
        )

    @classmethod
    def _operation(
        cls,
        value: Any,
    ) -> DeploymentUpdateOperation:
        if not isinstance(value, dict):
            raise DeploymentUpdateDefinitionError(
                "Each operation must be an object.",
            )

        action = value.get("action")
        if not isinstance(action, str):
            raise DeploymentUpdateDefinitionError(
                "Operation 'action' must be a string.",
            )

        action = action.strip().lower()

        if action not in cls.ACTIONS:
            raise DeploymentUpdateDefinitionError(
                f"Unsupported operation '{action}'.",
            )

        field = value.get("field")

        if not isinstance(field, str) or not field.strip():
            raise DeploymentUpdateDefinitionError(
                "Operation 'field' must be a non-empty string.",
            )

        field = field.strip().lower()

        if field not in cls.FIELDS:
            raise DeploymentUpdateDefinitionError(
                f"Unsupported Deployment field '{field}'. "
                f"Supported values: "
                f"{', '.join(sorted(cls.FIELDS))}.",
            )

        container = cls._resolve_container(
            field=field,
            value=value.get("container"),
        )

        operation_value = cls._resolve_value(
            action=action,
            field=field,
            value=value.get("value"),
        )

        return DeploymentUpdateOperation(
            action=action,
            field=field,
            container=container,
            value=operation_value,
        )

    @classmethod
    def _resolve_container(
        cls,
        *,
        field: str,
        value: Any,
    ) -> str | None:
        if field not in cls.CONTAINER_FIELDS:
            if value is not None:
                raise DeploymentUpdateDefinitionError(
                    f"Operation for field '{field}' does not "
                    f"support 'container'.",
                )

            return None

        if not isinstance(value, str) or not value.strip():
            raise DeploymentUpdateDefinitionError(
                f"Operation for field '{field}' requires "
                f"a non-empty 'container'.",
            )

        return value.strip()

    @classmethod
    def _resolve_value(
        cls,
        *,
        action: str,
        field: str,
        value: Any,
    ) -> Any:
        if value is None:
            if action in {"add", "update", "delete"}:
                raise DeploymentUpdateDefinitionError(
                    f"Operation for field '{field}' requires "
                    f"'value'.",
                )

        if field == "image":
            if not isinstance(value, str) or not value.strip():
                raise DeploymentUpdateDefinitionError(
                    f"Operation for field '{field}' requires "
                    f"a non-empty string 'value'.",
                )

            return value.strip()

        if field in cls.OBJECT_FIELDS:
            if not isinstance(value, dict) or not value:
                raise DeploymentUpdateDefinitionError(
                    f"Operation for field '{field}' requires "
                    f"a non-empty object 'value'.",
                )

            return value

        raise DeploymentUpdateDefinitionError(
            f"Unsupported Deployment field '{field}'.",
        )
