"""
ConfigMap/Secret update definition validator.
"""

from __future__ import annotations

from typing import Any

from .exceptions import UpdateDefinitionError
from .model import (
    ConfigMapSecretResource,
    ConfigMapSecretSource,
    ConfigMapSecretUpdate,
    UpdateOperation,
    UpdateTarget,
    SourceType,
)


class ConfigMapSecretUpdateValidator:
    """
    Validate and convert ConfigMap/Secret source definitions.

    Supported source documents:

    1. entropy/v1 ConfigMapSecretUpdate
    2. native v1 ConfigMap
    3. native v1 Secret
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

    NATIVE_KINDS = {
        "ConfigMap",
        "Secret",
    }

    NATIVE_API_VERSIONS = {
        "v1",
    }

    @classmethod
    def parse(
        cls,
        value: Any,
        *,
        path=None,
    ) -> ConfigMapSecretSource:
        """
        Validate and convert one source document.
        """

        if not isinstance(
            value,
            dict,
        ):

            raise UpdateDefinitionError(
                "Source definition must be an object.",
            )

        api_version = value.get(
            "apiVersion",
        )

        kind = value.get(
            "kind",
        )

        if (
            api_version == cls.API_VERSION
            and kind == cls.KIND
        ):

            return ConfigMapSecretSource(
                source_type=SourceType.UPDATE,
                path=path,
                update=cls._parse_update(
                    value,
                ),
            )

        if (
            api_version in cls.NATIVE_API_VERSIONS
            and kind in cls.NATIVE_KINDS
        ):

            return ConfigMapSecretSource(
                source_type=SourceType.RESOURCE,
                path=path,
                resource=cls._parse_resource(
                    value,
                ),
            )

        raise UpdateDefinitionError(
            f"Unsupported source definition "
            f"'{api_version}/{kind}'. "
            f"Expected '{cls.API_VERSION}/{cls.KIND}', "
            "ConfigMap, or Secret.",
        )

    # ------------------------------------------------------------------
    # Update definition
    # ------------------------------------------------------------------

    @classmethod
    def _parse_update(
        cls,
        value: dict[str, Any],
    ) -> ConfigMapSecretUpdate:
        """
        Validate an entropy/v1 update definition.
        """

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
            api_version=cls.API_VERSION,
            kind=cls.KIND,
            target=target,
            operations=parsed_operations,
        )

    # ------------------------------------------------------------------
    # Native resource
    # ------------------------------------------------------------------

    @classmethod
    def _parse_resource(
        cls,
        value: dict[str, Any],
    ) -> ConfigMapSecretResource:
        """
        Validate a native ConfigMap or Secret resource.
        """

        kind = value.get(
            "kind",
        )

        if kind not in cls.NATIVE_KINDS:

            raise UpdateDefinitionError(
                f"Unsupported native resource kind '{kind}'. "
                "Expected ConfigMap or Secret.",
            )

        metadata = value.get(
            "metadata",
        )

        if not isinstance(
            metadata,
            dict,
        ):

            raise UpdateDefinitionError(
                f"Native {kind} must contain "
                "'metadata' as an object.",
            )

        name = metadata.get(
            "name",
        )

        if (
            not isinstance(
                name,
                str,
            )
            or not name.strip()
        ):

            raise UpdateDefinitionError(
                f"Native {kind} must contain a "
                "non-empty metadata.name.",
            )

        data = value.get(
            "data",
        )

        if data is not None and not isinstance(
            data,
            dict,
        ):

            raise UpdateDefinitionError(
                f"Native {kind} 'data' must be an object.",
            )

        return ConfigMapSecretResource(
            api_version=value.get(
                "apiVersion",
            ),
            kind=kind,
            name=name.strip(),
            document=value,
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

        if (
            not isinstance(
                name,
                str,
            )
            or not name.strip()
        ):

            raise UpdateDefinitionError(
                "Target 'name' must be a non-empty string.",
            )

        return UpdateTarget(
            kind=kind,
            name=name.strip(),
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

        if (
            not isinstance(
                key,
                str,
            )
            or not key.strip()
        ):

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

        if action == "delete":

            return cls._delete_operation(
                value,
                key,
                operation_format,
            )

        return cls._write_operation(
            value,
            action,
            key,
            operation_format,
        )

    # ------------------------------------------------------------------
    # Delete operation
    # ------------------------------------------------------------------

    @classmethod
    def _delete_operation(
        cls,
        value: dict[str, Any],
        key: str,
        operation_format: str | None,
    ) -> UpdateOperation:
        """
        Validate a delete operation.

        Top-level delete:

            action: delete
            key: environment

        Structured delete:

            action: delete
            key: application.properties
            format: properties
            entries:
              - application.debug
        """

        if "value" in value:

            raise UpdateDefinitionError(
                f"Delete operation for key '{key}' "
                "cannot specify 'value'.",
            )

        entries = value.get(
            "entries",
        )

        if operation_format is None:

            if entries is not None:

                raise UpdateDefinitionError(
                    f"Top-level delete operation for key "
                    f"'{key}' cannot specify 'entries' "
                    "without a format.",
                )

            return UpdateOperation(
                action="delete",
                key=key,
            )

        if not isinstance(
            entries,
            list,
        ):

            raise UpdateDefinitionError(
                f"Delete operation for key '{key}' "
                f"with format '{operation_format}' "
                "requires 'entries' to be an array.",
            )

        if not entries:

            raise UpdateDefinitionError(
                f"Delete operation for key '{key}' "
                "cannot contain an empty 'entries' array.",
            )

        for entry in entries:

            if (
                not isinstance(
                    entry,
                    str,
                )
                or not entry.strip()
            ):

                raise UpdateDefinitionError(
                    f"Delete entries for key '{key}' "
                    "must contain non-empty strings.",
                )

        return UpdateOperation(
            action="delete",
            key=key,
            format=operation_format,
            entries=[
                entry.strip()
                for entry in entries
            ],
        )

    # ------------------------------------------------------------------
    # Add / update operation
    # ------------------------------------------------------------------

    @classmethod
    def _write_operation(
        cls,
        value: dict[str, Any],
        action: str,
        key: str,
        operation_format: str | None,
    ) -> UpdateOperation:
        """
        Validate add/update operations.
        """

        entries = value.get(
            "entries",
        )

        if operation_format is not None:

            if entries is None:

                raise UpdateDefinitionError(
                    f"Operation for key '{key}' "
                    f"with format '{operation_format}' "
                    "requires 'entries'.",
                )

            if not isinstance(
                entries,
                dict,
            ):

                raise UpdateDefinitionError(
                    f"Entries for key '{key}' "
                    f"with format '{operation_format}' "
                    "must be an object.",
                )

            if "value" in value:

                raise UpdateDefinitionError(
                    f"Structured operation for key '{key}' "
                    "cannot specify 'value'. "
                    "Use 'entries'.",
                )

            return UpdateOperation(
                action=action,
                key=key,
                format=operation_format,
                entries=entries,
            )

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
        )
