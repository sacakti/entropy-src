"""
ConfigMap/Secret update orchestrator.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from .adapter import ConfigMapSecretTarget
from .engine import ConfigMapSecretUpdateEngine
from .exceptions import UpdateFileError
from .index import ConfigMapSecretTargetIndex
from .model import (
    ConfigMapSecretUpdate,
    UpdateError,
    UpdateOperation,
    UpdateResult,
    UpdateSummary,
)
from .target_loader import TargetFile, TargetResource


class ConfigMapSecretUpdater:
    """
    Orchestrates ConfigMap/Secret resource updates.

    The updater coordinates:

        source definitions
            ↓
        target lookup
            ↓
        update/create
            ↓
        target file persistence
    """

    def __init__(
        self,
        engine: ConfigMapSecretUpdateEngine,
        filesystem,
    ) -> None:

        self._engine = engine
        self._filesystem = filesystem

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        definitions: list[ConfigMapSecretUpdate],
        resources: list[TargetResource],
        *,
        target_directory: Path,
        replace: bool = False,
    ) -> UpdateSummary:
        """
        Apply all update definitions.

        Definitions targeting the same ConfigMap or Secret are
        processed as one atomic transaction.

        A failure in one resource does not prevent other resources
        from being processed.
        """

        index = ConfigMapSecretTargetIndex(
            resources,
        )

        groups = self._group_definitions(
            definitions,
        )

        results: list[UpdateResult] = []
        errors: list[UpdateError] = []
        changed_paths: set[Path] = set()

        for identity, group in groups.items():

            kind, name = identity

            resource = index.get(
                kind,
                name,
            )

            try:

                if resource is None:

                    result = self._create_group(group, target_directory, replace)

                else:

                    result = self._update_group(
                        resource,
                        group,
                        replace,
                    )

                    changed_paths.add(
                        resource.target_file.path,
                    )

                results.append(
                    result,
                )

            except Exception as exc:

                errors.append(
                    UpdateError(
                        kind=kind,
                        name=name,
                        path=(
                            resource.target_file.path if resource is not None else target_directory
                        ),
                        key=self._error_key(
                            group,
                            exc,
                        ),
                        message=str(
                            exc,
                        ),
                    ),
                )

        self._write_changed_files(
            resources,
            changed_paths,
        )

        return UpdateSummary(
            results=results,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Existing files
    # ------------------------------------------------------------------

    def _write_changed_files(
        self,
        resources: list[TargetResource],
        changed_paths: set[Path],
    ) -> None:
        """
        Persist modified target files.

        Each TargetFile contains all YAML documents from the
        original file, so unrelated resources are preserved.
        """

        files: dict[Path, TargetFile] = {}

        for resource in resources:

            path = resource.target_file.path

            if path not in changed_paths:
                continue

            files[path] = resource.target_file

        for target_file in files.values():

            data = self._filesystem.serialize_yaml_documents(
                target_file.documents,
            )

            self._filesystem.write_text(
                target_file.path,
                data,
            )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _write_new_file(
        self,
        path: Path,
        document: dict[str, Any],
    ) -> None:
        """
        Write a newly created resource.
        """

        data = self._filesystem.serialize_yaml_documents(
            [document],
        )

        self._filesystem.write_text(
            path,
            data,
        )

    def _normalize_for_replace(
        self,
        resource: TargetResource,
        definition: ConfigMapSecretUpdate,
    ) -> tuple[
        ConfigMapSecretUpdate,
        set[str],
    ]:
        """
        Normalize operations for replacement mode.

        An add operation targeting an existing top-level key
        becomes an update operation.

        Returns the normalized definition together with the
        keys whose add operations were replaced by updates.
        """

        adapter = ConfigMapSecretTarget(
            resource.document,
            definition.target.kind,
        )

        operations: list[UpdateOperation] = []

        replaced_add_keys: set[str] = set()

        for operation in definition.operations:

            if operation.action == "add" and adapter.contains(
                operation.key,
            ):

                replaced_add_keys.add(
                    operation.key,
                )

                operations.append(
                    UpdateOperation(
                        action="update",
                        key=operation.key,
                        value=operation.value,
                        format=operation.format,
                        entries=operation.entries,
                    ),
                )

            else:

                operations.append(
                    operation,
                )

        return (
            ConfigMapSecretUpdate(
                api_version=definition.api_version,
                kind=definition.kind,
                target=definition.target,
                operations=operations,
            ),
            replaced_add_keys,
        )

    @staticmethod
    def _error_key(
        definitions: list[ConfigMapSecretUpdate],
        error: Exception,
    ) -> str | None:
        """
        Identify the operation key associated with an error.
        """

        message = str(
            error,
        )

        for definition in definitions:

            for operation in definition.operations:

                if operation.key in message:

                    return operation.key

        return None

    def _group_definitions(
        self,
        definitions: list[ConfigMapSecretUpdate],
    ) -> dict[
        tuple[str, str],
        list[ConfigMapSecretUpdate],
    ]:
        """
        Group update definitions by target identity.

        Multiple source YAML documents may target the same
        ConfigMap or Secret. They must be processed as one
        transaction.
        """

        grouped: dict[
            tuple[str, str],
            list[ConfigMapSecretUpdate],
        ] = defaultdict(list)

        for definition in definitions:

            identity = (
                definition.target.kind,
                definition.target.name,
            )

            grouped[identity].append(
                definition,
            )

        return dict(
            grouped,
        )

    def _update_group(
        self,
        resource: TargetResource,
        definitions: list[ConfigMapSecretUpdate],
        replace: bool,
    ) -> UpdateResult:
        """
        Apply all definitions targeting one resource atomically.
        """

        working_document = deepcopy(
            resource.document,
        )

        changes: list[dict[str, Any]] = []

        replaced_add_keys: set[str] = set()

        for definition in definitions:

            effective_definition = definition

            if replace:

                working_resource = TargetResource(
                    kind=resource.kind,
                    name=resource.name,
                    document=working_document,
                    target_file=resource.target_file,
                    document_index=resource.document_index,
                )

                (
                    effective_definition,
                    definition_replaced_add_keys,
                ) = self._normalize_for_replace(
                    working_resource,
                    definition,
                )

                replaced_add_keys.update(
                    definition_replaced_add_keys,
                )

            changes.extend(
                self._engine.apply(
                    working_document,
                    effective_definition,
                    replace=replace,
                ),
            )

        if replace:

            managed_keys = {
                operation.key for definition in definitions for operation in definition.operations
            }

            changes.extend(
                self._engine.prune(
                    working_document,
                    managed_keys,
                ),
            )

        # Annotate operations that were originally "add"
        # but were converted to "update" in replace mode.
        for change in changes:

            if change.get("action") == "update" and change.get("key") in replaced_add_keys:

                change["status"] = "replaced_add"

        # Commit only after every operation succeeds.
        resource.document.clear()

        resource.document.update(
            working_document,
        )

        return UpdateResult(
            kind=resource.kind,
            name=resource.name,
            path=resource.target_file.path,
            created=False,
            changes=changes,
        )

    def _create_group(
        self, definitions: list[ConfigMapSecretUpdate], target_directory: Path, replace
    ) -> UpdateResult:
        """
        Create one resource from multiple definitions atomically.
        """

        first = definitions[0]

        document: dict[str, Any] = {
            "apiVersion": "v1",
            "kind": first.target.kind,
            "metadata": {
                "name": first.target.name,
            },
        }

        changes: list[dict[str, Any]] = []

        for definition in definitions:

            changes.extend(
                self._engine.apply(document, definition, replace=replace),
            )

        path = target_directory / (f"{first.target.kind.lower()}-" f"{first.target.name}.yaml")

        if self._filesystem.exists(
            path,
        ):

            raise UpdateFileError(
                f"Cannot create target resource "
                f"'{first.target.kind}/"
                f"{first.target.name}': "
                f"file '{path}' already exists.",
            )

        self._write_new_file(
            path,
            document,
        )

        return UpdateResult(
            kind=first.target.kind,
            name=first.target.name,
            path=path,
            created=True,
            changes=changes,
        )
