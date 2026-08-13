"""
ConfigMap/Secret update definition validator.
"""

from __future__ import annotations

from typing import Any

from .exceptions import UpdateDefinitionError
from .model import (
    ConfigMapSecretUpdate,
    UpdateOperation,
    UpdateTarget,
)


class ConfigMapSecretUpdateValidator:
    """
    Validate and convert a ConfigMap/Secret update definition.
    """

    API_VERSION = "entropy/v1"

    KIND = "ConfigMapSecretUpdate"

    TARGET_KINDS = {
        "ConfigMap",
        "Secret",
    }

    ACTIONS = {
        "add",
        "update",
        "delete",
    }

    FORMATS = {
        "properties",
        "yaml",
    }

    @classmethod
    def parse(
        cls,
        value: Any,
    ) -> ConfigMapSecretUpdate:
        """
        Validate an update definition and return its model.
        """

        if not isinstance(
            value,
            dict,
        ):

            raise UpdateDefinitionError(
                "Update definition must be an object.",
            )

        api_version = value.get(
            "apiVersion",
        )

        if api_version != cls.API_VERSION:

            raise UpdateDefinitionError(
                f"Unsupported apiVersion '{api_version}'. "
                f"Expected '{cls.API_VERSION}'.",
            )

        kind = value.get(
            "kind",
        )

        if kind != cls.KIND:

            raise UpdateDefinitionError(
                f"Invalid update definition kind '{kind}'. "
                f"Expected '{cls.KIND}'.",
            )

        target = cls._target(
            value.get(
                "target",
            ),
        )

        operations = value.get(
            "operations",
        )

        if not isinstance(
            operations,
            list,
        ):

            raise UpdateDefinitionError(
                "'operations' must be an array.",
            )

        if not operations:

            raise UpdateDefinitionError(
                "'operations' cannot be empty.",
            )

        parsed_operations = [
            cls._operation(
                item,
            )
            for item in operations
        ]

        return ConfigMapSecretUpdate(
            api_version=api_version,
            kind=kind,
            target=target,
            operations=parsed_operations,
        )

    # ------------------------------------------------------------------
    # Target
    # ------------------------------------------------------------------

    @classmethod
    def _target(
        cls,
        value: Any,
    ) -> UpdateTarget:
        """
        Validate the update target.
        """

        if not isinstance(
            value,
            dict,
        ):

            raise UpdateDefinitionError(
                "'target' must be an object.",
            )

        kind = value.get(
            "kind",
        )

        if kind not in cls.TARGET_KINDS:

            raise UpdateDefinitionError(
                f"Unsupported target kind '{kind}'. "
                "Supported values: ConfigMap, Secret.",
            )

        name = value.get(
            "name",
        )

        if not isinstance(
            name,
            str,
        ) or not name.strip():

            raise UpdateDefinitionError(
                "Target 'name' must be a non-empty string.",
            )

        return UpdateTarget(
            kind=kind,
            name=name,
        )

    # ------------------------------------------------------------------
    # Operation
    # ------------------------------------------------------------------

    @classmethod
    def _operation(
        cls,
        value: Any,
    ) -> UpdateOperation:
        """
        Validate one update operation.
        """

        if not isinstance(
            value,
            dict,
        ):

            raise UpdateDefinitionError(
                "Each operation must be an object.",
            )

        action = value.get(
            "action",
        )

        if not isinstance(
            action,
            str,
        ):

            raise UpdateDefinitionError(
                "Operation 'action' must be a string.",
            )

        action = action.strip().lower()

        if action not in cls.ACTIONS:

            raise UpdateDefinitionError(
                f"Unsupported operation '{action}'. "
                "Supported values: add, update, delete.",
            )

        key = value.get(
            "key",
        )

        if not isinstance(
            key,
            str,
        ) or not key.strip():

            raise UpdateDefinitionError(
                "Operation 'key' must be a non-empty string.",
            )

        key = key.strip()

        operation_format = value.get(
            "format",
        )

        if operation_format is not None:

            if not isinstance(
                operation_format,
                str,
            ):

                raise UpdateDefinitionError(
                    f"Format for key '{key}' "
                    "must be a string.",
                )

            operation_format = operation_format.strip().lower()

            if operation_format not in cls.FORMATS:

                raise UpdateDefinitionError(
                    f"Unsupported format '{operation_format}' "
                    f"for key '{key}'. "
                    "Supported values: properties, yaml.",
                )

        entries = value.get(
            "entries",
        )

        if entries is not None and not isinstance(
            entries,
            dict,
        ):

            raise UpdateDefinitionError(
                f"'entries' for key '{key}' "
                "must be an object.",
            )

        if action == "delete":

            if operation_format is not None:

                raise UpdateDefinitionError(
                    f"Delete operation for key '{key}' "
                    "cannot specify 'format'.",
                )

            if entries is not None:

                raise UpdateDefinitionError(
                    f"Delete operation for key '{key}' "
                    "cannot specify 'entries'.",
                )

            if "value" in value:

                raise UpdateDefinitionError(
                    f"Delete operation for key '{key}' "
                    "cannot specify 'value'.",
                )

        elif operation_format is not None:

            if operation_format not in cls.FORMATS:

                raise UpdateDefinitionError(
                    f"Unsupported format '{operation_format}'.",
                )

            if entries is None:

                raise UpdateDefinitionError(
                    f"Operation for key '{key}' "
                    f"with format '{operation_format}' "
                    "requires 'entries'.",
                )

            if "value" in value:

                raise UpdateDefinitionError(
                    f"Structured operation for key '{key}' "
                    "cannot specify 'value'. "
                    "Use 'entries'.",
                )

        else:

            if "value" not in value:

                raise UpdateDefinitionError(
                    f"Operation for key '{key}' "
                    "requires 'value'.",
                )

            if entries is not None:

                raise UpdateDefinitionError(
                    f"Scalar operation for key '{key}' "
                    "cannot specify 'entries'.",
                )

        return UpdateOperation(
            action=action,
            key=key,
            value=value.get(
                "value",
            ),
            format=operation_format,
            entries=entries,
        )
