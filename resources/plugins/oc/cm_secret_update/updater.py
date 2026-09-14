"""
ConfigMap/Secret update orchestrator.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from .engine import ConfigMapSecretUpdateEngine
from .exceptions import UpdateFileError
from .index import ConfigMapSecretTargetIndex
from .model import (
    ConfigMapSecretSource,
    SourceType,
    UpdateError,
    UpdateResult,
    UpdateSummary,
)
from .target_loader import TargetFile, TargetResource


class ConfigMapSecretUpdater:
    """
    Orchestrate ConfigMap/Secret source definitions.

    Sources may be either:

    - entropy/v1 ConfigMapSecretUpdate definitions
    - native ConfigMap/Secret resources

    Update definitions are always non-destructive.

    Native resources are merged by default and completely replaced
    only when replace=True.
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
        sources: list[ConfigMapSecretSource],
        resources: list[TargetResource],
        *,
        target_directory: Path,
        replace: bool = False,
    ) -> UpdateSummary:
        """
        Apply all ConfigMap/Secret sources.
        """

        index = ConfigMapSecretTargetIndex(
            resources,
        )

        results: list[UpdateResult] = []
        errors: list[UpdateError] = []
        changed_paths: set[Path] = set()

        grouped = self._group_sources(
            sources,
        )

        for identity, group in grouped.items():

            kind, name = identity

            resource = index.get(
                kind,
                name,
            )

            try:

                if resource is None:

                    result = self._create_group(
                        group,
                        target_directory,
                    )

                else:

                    result = self._update_group(
                        resource,
                        group,
                        replace=replace,
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
                        message=str(exc),
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

        All documents in each TargetFile are preserved.
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
    # New files
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

    # ------------------------------------------------------------------
    # Existing group
    # ------------------------------------------------------------------

    def _update_group(
        self,
        resource: TargetResource,
        sources: list[ConfigMapSecretSource],
        *,
        replace: bool,
    ) -> UpdateResult:
        """
        Apply all sources targeting one resource atomically.
        """

        working_document = deepcopy(
            resource.document,
        )

        changes: list[dict[str, Any]] = []

        for source in sources:

            if source.source_type == SourceType.UPDATE:

                assert source.update is not None

                changes.extend(
                    self._engine.apply(
                        working_document,
                        source.update,
                    ),
                )

                continue

            assert source.resource is not None

            changes.extend(
                self._merge_native_resource(
                    working_document,
                    source.resource.document,
                    replace=replace,
                ),
            )

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

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def _create_group(
        self,
        sources: list[ConfigMapSecretSource],
        target_directory: Path,
    ) -> UpdateResult:
        """
        Create one ConfigMap or Secret from one or more sources.
        """

        first = sources[0]

        document = self._initial_document(
            first,
        )

        changes: list[dict[str, Any]] = []

        for source in sources:

            if source.source_type == SourceType.UPDATE:

                assert source.update is not None

                changes.extend(
                    self._engine.apply(
                        document,
                        source.update,
                    ),
                )

                continue

            assert source.resource is not None

            document = deepcopy(
                source.resource.document,
            )

            changes.append(
                {
                    "action": "create",
                    "key": None,
                    "status": "created",
                    "source": "native",
                },
            )

        path = target_directory / (f"{first.kind.lower()}-" f"{first.name}.yaml")

        if self._filesystem.exists(
            path,
        ):

            raise UpdateFileError(
                f"Cannot create target resource "
                f"'{first.kind}/{first.name}': "
                f"file '{path}' already exists.",
            )

        self._write_new_file(
            path,
            document,
        )

        return UpdateResult(
            kind=first.kind,
            name=first.name,
            path=path,
            created=True,
            changes=changes,
        )

    # ------------------------------------------------------------------
    # Native resource
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_native_resource(
        target: dict[str, Any],
        source: dict[str, Any],
        *,
        replace: bool,
    ) -> list[dict[str, Any]]:
        """
        Merge or replace a native ConfigMap/Secret resource.

        replace=False:
            Merge explicitly supplied fields while preserving unrelated
            target fields.

        replace=True:
            Replace the complete resource.
        """

        if replace:

            target.clear()

            target.update(
                deepcopy(
                    source,
                ),
            )

            return [
                {
                    "action": "replace",
                    "key": None,
                    "status": "replaced",
                    "source": "native",
                },
            ]

        changes: list[dict[str, Any]] = []

        source_data = source.get(
            "data",
            {},
        )

        if not isinstance(
            source_data,
            dict,
        ):

            raise UpdateFileError(
                "Native ConfigMap/Secret 'data' must be an object.",
            )

        target_data = target.setdefault(
            "data",
            {},
        )

        if not isinstance(
            target_data,
            dict,
        ):

            raise UpdateFileError(
                "Target ConfigMap/Secret 'data' must be an object.",
            )

        for key, value in source_data.items():

            status = "updated" if key in target_data else "added"

            target_data[key] = deepcopy(
                value,
            )

            changes.append(
                {
                    "action": "update",
                    "key": key,
                    "status": status,
                    "source": "native",
                },
            )

        return changes

    # ------------------------------------------------------------------
    # Initial document
    # ------------------------------------------------------------------

    @staticmethod
    def _initial_document(
        source: ConfigMapSecretSource,
    ) -> dict[str, Any]:
        """
        Create the initial resource document for a new target.
        """

        if source.source_type == SourceType.RESOURCE:

            assert source.resource is not None

            return deepcopy(
                source.resource.document,
            )

        assert source.update is not None

        return {
            "apiVersion": "v1",
            "kind": source.update.target.kind,
            "metadata": {
                "name": source.update.target.name,
            },
        }

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    @staticmethod
    def _group_sources(
        sources: list[ConfigMapSecretSource],
    ) -> dict[
        tuple[str, str],
        list[ConfigMapSecretSource],
    ]:
        """
        Group sources by ConfigMap/Secret identity.

        Multiple YAML documents may target the same resource.
        """

        grouped: dict[
            tuple[str, str],
            list[ConfigMapSecretSource],
        ] = defaultdict(list)

        for source in sources:

            grouped[
                (
                    source.kind,
                    source.name,
                )
            ].append(
                source,
            )

        return dict(
            grouped,
        )

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------

    @staticmethod
    def _error_key(
        sources: list[ConfigMapSecretSource],
        error: Exception,
    ) -> str | None:
        """
        Identify the operation key associated with an error.
        """

        message = str(
            error,
        )

        for source in sources:

            if source.source_type != SourceType.UPDATE:

                continue

            assert source.update is not None

            for operation in source.update.operations:

                if operation.key in message:

                    return operation.key

        return None
