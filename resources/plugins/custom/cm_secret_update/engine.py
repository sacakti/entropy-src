"""
ConfigMap/Secret update engine.
"""

from __future__ import annotations

from typing import Any, Callable

from .exceptions import (
    UpdateKeyAlreadyExistsError,
    UpdateKeyNotFoundError,
    UnsupportedUpdateFormatError,
    UpdateTargetError,
)
from .model import (
    ConfigMapSecretUpdate,
    UpdateOperation,
)
from .adapter import ConfigMapSecretTarget
from .properties import PropertiesUpdater

class ConfigMapSecretUpdateEngine:
    """
    Applies ConfigMap/Secret update operations.
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
        Apply ConfigMap/Secret update operations.
        """

        adapter = ConfigMapSecretTarget(
            target,
            definition.target.kind,
        )

        changes: list[dict[str, Any]] = []

        for operation in definition.operations:

            changes.append(
                self._apply_operation(
                    adapter,
                    operation,
                    replace=replace,
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
        *,
        replace: bool = False,
    ) -> dict[str, Any]:

        if operation.action == "add":

            return self._add(
                target,
                operation,
            )

        if operation.action == "update":

            return self._update(
                target,
                operation,
            )

        return self._delete(
            target,
            operation,
            replace=replace,
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

        if target.contains(
            key,
        ):

            raise UpdateKeyAlreadyExistsError(
                f"Cannot add key '{key}': "
                "key already exists.",
            )

        value = self._value(
            None,
            operation,
        )

        target.set(
            key,
            value,
        )

        return {
            "action": "add",
            "key": key,
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

        if not target.contains(
            key,
        ):

            raise UpdateKeyNotFoundError(
                f"Cannot update key '{key}': "
                "key does not exist.",
            )

        old = target.get(
            key,
        )

        value = self._value(
            old,
            operation,
        )

        target.set(
            key,
            value,
        )

        return {
            "action": "update",
            "key": key,
        }

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    @staticmethod
    def _delete(
        target: ConfigMapSecretTarget,
        operation: UpdateOperation,
        *,
        replace: bool = False,
    ) -> dict[str, Any]:

        key = operation.key

        if not target.contains(
            key,
        ):

            if replace:

                return {
                    "action": "delete",
                    "key": key,
                    "status": "unchanged",
                }

            raise UpdateKeyNotFoundError(
                f"Cannot delete key '{key}': "
                "key does not exist.",
            )

        target.delete(
            key,
        )

        return {
            "action": "delete",
            "key": key,
            "status": "deleted",
        }

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

    def _yaml_update(
        self,
        existing: Any,
        operation: UpdateOperation,
    ) -> Any:

        if self._yaml_loader is None:
            raise RuntimeError(
                "YAML loader is not configured.",
            )

        if self._yaml_dumper is None:
            raise RuntimeError(
                "YAML dumper is not configured.",
            )

        if not isinstance(
            existing,
            str,
        ):

            raise UpdateTargetError(
                f"Embedded YAML value for key "
                f"'{operation.key}' must be a string.",
            )

        current = self._yaml_loader(
            existing,
        )

        if not isinstance(
            current,
            dict,
        ):

            raise UpdateTargetError(
                f"Embedded YAML value for key "
                f"'{operation.key}' must contain an object.",
            )

        self._merge(
            current,
            operation.entries or {},
        )

        return self._yaml_dumper(
            current,
        )

    @classmethod
    def _merge(
        cls,
        target: Any,
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

    def _properties_update(
        self,
        existing: Any,
        operation: UpdateOperation,
    ) -> str:

        if not isinstance(
            existing,
            str,
        ):

            raise UpdateTargetError(
                f"Embedded properties value for key "
                f"'{operation.key}' must be a string.",
            )

        return self._properties.update(
            existing,
            operation.entries or {},
        )

    def prune(
        self,
        target: dict[str, Any],
        managed_keys: set[str],
    ) -> list[dict[str, Any]]:
        """
        Remove top-level data keys that are not managed
        by the source definitions.
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
                },
            )

        return changes
