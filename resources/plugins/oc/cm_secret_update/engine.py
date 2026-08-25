"""
ConfigMap/Secret update engine.
"""

from __future__ import annotations

from typing import Any, Callable

from .adapter import ConfigMapSecretTarget
from .exceptions import (
    DeploymentUpdateTargetError,
    UnsupportedUpdateFormatError,
)
from .model import (
    ConfigMapSecretUpdate,
    UpdateOperation,
)
from .properties import PropertiesUpdater


class ConfigMapSecretUpdateEngine:
    """
    Apply ConfigMap/Secret update operations.

    Operation semantics are intentionally idempotent:

    - add:
        existing -> replace existing value
        missing  -> add value

    - update:
        existing -> update value
        missing  -> add value

    - delete:
        existing -> delete value
        missing  -> leave unchanged

    Structured properties/YAML operations follow the same
    override semantics.
    """

    def __init__(
        self,
        yaml_loader: Callable[[str], Any] | None = None,
        yaml_dumper: Callable[[Any], str] | None = None,
        properties_updater: PropertiesUpdater | None = None,
    ) -> None:

        self._yaml_loader = yaml_loader
        self._yaml_dumper = yaml_dumper

        self._properties = (
            properties_updater
            if properties_updater is not None
            else PropertiesUpdater()
        )

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(
        self,
        target: dict[str, Any],
        definition: ConfigMapSecretUpdate,
        *,
        replace: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Apply update operations to an existing target.

        ``replace`` is retained for API compatibility. It does not make
        individual update operations destructive. Complete-resource
        replacement is handled by the plugin for native resources.
        """

        del replace

        adapter = ConfigMapSecretTarget(
            target,
            definition.target.kind,
        )

        changes: list[dict[str, Any]] = []

        for operation in definition.operations:

            changes.extend(
                self._apply_operation(
                    adapter,
                    operation,
                ),
            )

        return changes

    # ------------------------------------------------------------------
    # Operation
    # ------------------------------------------------------------------

    def _apply_operation(
        self,
        target: ConfigMapSecretTarget,
        operation: UpdateOperation,
    ) -> list[dict[str, Any]]:

        if operation.action == "add":

            return [
                self._add(
                    target,
                    operation,
                ),
            ]

        if operation.action == "update":

            return [
                self._update(
                    target,
                    operation,
                ),
            ]

        return self._delete(
            target,
            operation,
        )

    # ------------------------------------------------------------------
    # Add
    # ------------------------------------------------------------------

    def _add(
        self,
        target: ConfigMapSecretTarget,
        operation: UpdateOperation,
    ) -> dict[str, Any]:

        key = operation.key
        existed = target.contains(
            key,
        )

        existing = (
            target.get(key)
            if existed
            else None
        )

        value = self._value(
            existing,
            operation,
        )

        target.set(
            key,
            value,
        )

        return {
            "action": "add",
            "key": key,
            "status": (
                "replaced_existing"
                if existed
                else "added"
            ),
        }

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def _update(
        self,
        target: ConfigMapSecretTarget,
        operation: UpdateOperation,
    ) -> dict[str, Any]:

        key = operation.key
        existed = target.contains(
            key,
        )

        existing = (
            target.get(key)
            if existed
            else None
        )

        value = self._value(
            existing,
            operation,
        )

        target.set(
            key,
            value,
        )

        return {
            "action": "update",
            "key": key,
            "status": (
                "updated"
                if existed
                else "added_missing"
            ),
        }

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete(
        self,
        target: ConfigMapSecretTarget,
        operation: UpdateOperation,
    ) -> list[dict[str, Any]]:

        key = operation.key

        if operation.format is None:

            if not target.contains(
                key,
            ):

                return [
                    {
                        "action": "delete",
                        "key": key,
                        "status": "unchanged_missing",
                    },
                ]

            target.delete(
                key,
            )

            return [
                {
                    "action": "delete",
                    "key": key,
                    "status": "deleted",
                },
            ]

        if operation.format == "properties":

            return self._delete_properties(
                target,
                operation,
            )

        if operation.format == "yaml":

            return self._delete_yaml(
                target,
                operation,
            )

        raise UnsupportedUpdateFormatError(
            f"Unsupported update format "
            f"'{operation.format}'.",
        )

    # ------------------------------------------------------------------
    # Value
    # ------------------------------------------------------------------

    def _value(
        self,
        existing: Any,
        operation: UpdateOperation,
    ) -> Any:

        if operation.format is None:

            return operation.value

        if operation.format == "yaml":

            return self._yaml_update(
                existing,
                operation,
            )

        if operation.format == "properties":

            return self._properties_update(
                existing,
                operation,
            )

        raise UnsupportedUpdateFormatError(
            f"Unsupported update format "
            f"'{operation.format}'.",
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def _properties_update(
        self,
        existing: Any,
        operation: UpdateOperation,
    ) -> str:

        if existing is None:

            existing = ""

        if not isinstance(
            existing,
            str,
        ):

            raise DeploymentUpdateTargetError(
                f"Embedded properties value for key "
                f"'{operation.key}' must be a string.",
            )

        if not isinstance(
            operation.entries,
            dict,
        ):

            raise DeploymentUpdateTargetError(
                f"Properties operation for key "
                f"'{operation.key}' requires object entries.",
            )

        content, _ = self._properties.update(
            existing,
            operation.entries,
        )

        return content

    def _delete_properties(
        self,
        target: ConfigMapSecretTarget,
        operation: UpdateOperation,
    ) -> list[dict[str, Any]]:

        key = operation.key

        if not target.contains(
            key,
        ):

            return [
                {
                    "action": "delete",
                    "key": key,
                    "status": "unchanged_missing",
                },
            ]

        existing = target.get(
            key,
        )

        if not isinstance(
            existing,
            str,
        ):

            raise DeploymentUpdateTargetError(
                f"Embedded properties value for key "
                f"'{key}' must be a string.",
            )

        if not isinstance(
            operation.entries,
            list,
        ):

            raise DeploymentUpdateTargetError(
                f"Properties delete operation for key "
                f"'{key}' requires a list of property names.",
            )

        content, changes = self._properties.delete(
            existing,
            operation.entries,
        )

        target.set(
            key,
            content,
        )

        return [
            {
                "action": "delete",
                "key": key,
                "status": "updated",
                "entries": changes,
            },
        ]

    # ------------------------------------------------------------------
    # YAML
    # ------------------------------------------------------------------

    def _yaml_update(
        self,
        existing: Any,
        operation: UpdateOperation,
    ) -> Any:

        current = self._load_yaml(
            existing,
            operation.key,
        )

        if not isinstance(
            operation.entries,
            dict,
        ):

            raise DeploymentUpdateTargetError(
                f"YAML operation for key "
                f"'{operation.key}' requires object entries.",
            )

        self._merge(
            current,
            operation.entries,
        )

        return self._dump_yaml(
            current,
        )

    def _delete_yaml(
        self,
        target: ConfigMapSecretTarget,
        operation: UpdateOperation,
    ) -> list[dict[str, Any]]:

        key = operation.key

        if not target.contains(
            key,
        ):

            return [
                {
                    "action": "delete",
                    "key": key,
                    "status": "unchanged_missing",
                },
            ]

        existing = target.get(
            key,
        )

        current = self._load_yaml(
            existing,
            key,
        )

        if not isinstance(
            operation.entries,
            list,
        ):

            raise DeploymentUpdateTargetError(
                f"YAML delete operation for key "
                f"'{key}' requires a list of paths.",
            )

        changes: list[dict[str, Any]] = []

        for path in operation.entries:

            if not isinstance(
                path,
                str,
            ):

                raise DeploymentUpdateTargetError(
                    f"YAML delete path for key "
                    f"'{key}' must be a string.",
                )

            status = self._delete_yaml_path(
                current,
                path,
            )

            changes.append(
                {
                    "path": path,
                    "status": status,
                },
            )

        target.set(
            key,
            self._dump_yaml(
                current,
            ),
        )

        return [
            {
                "action": "delete",
                "key": key,
                "status": "updated",
                "entries": changes,
            },
        ]

    def _load_yaml(
        self,
        existing: Any,
        key: str,
    ) -> dict[str, Any]:

        if self._yaml_loader is None:

            raise RuntimeError(
                "YAML loader is not configured.",
            )

        if existing is None:

            return {}

        if not isinstance(
            existing,
            str,
        ):

            raise DeploymentUpdateTargetError(
                f"Embedded YAML value for key "
                f"'{key}' must be a string.",
            )

        current = self._yaml_loader(
            existing,
        )

        if current is None:

            return {}

        if not isinstance(
            current,
            dict,
        ):

            raise DeploymentUpdateTargetError(
                f"Embedded YAML value for key "
                f"'{key}' must contain an object.",
            )

        return current

    def _dump_yaml(
        self,
        value: dict[str, Any],
    ) -> str:

        if self._yaml_dumper is None:

            raise RuntimeError(
                "YAML dumper is not configured.",
            )

        return self._yaml_dumper(
            value,
        )

    @classmethod
    def _merge(
        cls,
        target: dict[str, Any],
        updates: dict[str, Any],
    ) -> None:

        for key, value in updates.items():

            if (
                key in target
                and isinstance(
                    target[key],
                    dict,
                )
                and isinstance(
                    value,
                    dict,
                )
            ):

                cls._merge(
                    target[key],
                    value,
                )

            else:

                target[key] = value

    @classmethod
    def _delete_yaml_path(
        cls,
        target: dict[str, Any],
        path: str,
    ) -> str:

        parts = [
            part.strip()
            for part in path.split(".")
            if part.strip()
        ]

        if not parts:

            return "unchanged_missing"

        current: Any = target

        for part in parts[:-1]:

            if not isinstance(
                current,
                dict,
            ):

                return "unchanged_missing"

            if part not in current:

                return "unchanged_missing"

            current = current[part]

        if not isinstance(
            current,
            dict,
        ):

            return "unchanged_missing"

        final_key = parts[-1]

        if final_key not in current:

            return "unchanged_missing"

        del current[final_key]

        return "deleted"

    # ------------------------------------------------------------------
    # Prune
    # ------------------------------------------------------------------

    def prune(
        self,
        target: dict[str, Any],
        managed_keys: set[str],
    ) -> list[dict[str, Any]]:
        """
        Remove top-level data keys that are not managed
        by the source definitions.

        This method is retained for compatibility but should only
        be called explicitly by the plugin when destructive pruning
        has been requested.
        """

        adapter = ConfigMapSecretTarget(
            target,
            target["kind"],
        )

        changes: list[dict[str, Any]] = []

        for key in sorted(
            adapter.keys() - managed_keys,
        ):

            adapter.delete(
                key,
            )

            changes.append(
                {
                    "action": "delete",
                    "key": key,
                    "status": "pruned",
                },
            )

        return changes
