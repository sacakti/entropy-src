"""
ConfigMap/Secret update plugin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .engine import ConfigMapSecretUpdateEngine
from .exceptions import ConfigMapSecretUpdateException
from .loader import ConfigMapSecretUpdateLoader
from .model import (
    ConfigMapSecretResource,
    ConfigMapSecretSource,
    ConfigMapSecretUpdate,
    SourceType,
    UpdateOperation,
    UpdateTarget,
)
from .target_loader import ConfigMapSecretTargetLoader
from .updater import ConfigMapSecretUpdater


class CmSecretUpdatePlugin(BasePlugin):
    """
    Update ConfigMap and Secret YAML definitions.
    """

    def execute(self) -> PluginResult:
        """
        Execute the ConfigMap/Secret update.
        """

        self.message.info(
            "Starting ConfigMap/Secret update.",
        )

        try:
            with self.activity(
                "cm_secret_updater",
            ):
                result = self._execute()

        except ConfigMapSecretUpdateException as exc:
            self.message.error(str(exc))

            return PluginResult(
                success=False,
                changed=False,
                outputs=dict(self.outputs),
                errors=[
                    {
                        "message": str(exc),
                    },
                ],
                metadata=self._metadata(),
            )

        if not result.success:
            return result

        self.message.success(
            "ConfigMap/Secret updated successfully.",
        )

        return result

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def _execute(self) -> PluginResult:
        """
        Execute ConfigMap/Secret updates.
        """

        mode = self.arguments.string(
            "mode",
            default="folder",
        )

        if mode is None:
            mode = "folder"

        mode = mode.strip().lower()

        if mode == "folder":
            return self._execute_folder()

        if mode == "deployments":
            return self._execute_deployments()

        raise ConfigMapSecretUpdateException(
            f"Unsupported mode '{mode}'. " "Expected 'folder' or 'deployments'.",
        )

    # ------------------------------------------------------------------
    # Folder mode
    # ------------------------------------------------------------------

    def _execute_folder(self) -> PluginResult:
        """
        Execute ConfigMap/Secret updates from source and target folders.
        """

        source = self._required_path("source")
        target = self._required_path("target")
        replace = self.arguments.boolean(
            "replace",
            False,
        )

        if replace is None:
            replace = False

        self._validate_directories(
            source,
            target,
        )

        self.message.info(
            f"Source: {source}",
        )

        self.message.info(
            f"Target: {target}",
        )

        self.message.info(
            f"Replace existing: {str(replace).lower()}",
        )

        source_loader = ConfigMapSecretUpdateLoader(
            filesystem=self.filesystem,
        )

        sources = source_loader.load_directory(
            source,
        )

        self.message.info(
            f"Loaded {len(sources)} ConfigMap/Secret source(s).",
        )

        target_loader = ConfigMapSecretTargetLoader(
            filesystem=self.filesystem,
        )

        resources = target_loader.load_directory(
            target,
        )

        self.message.info(
            f"Loaded {len(resources)} target resource(s).",
        )

        engine = ConfigMapSecretUpdateEngine(
            yaml_loader=self._parse_yaml,
            yaml_dumper=self._serialize_yaml,
        )

        updater = ConfigMapSecretUpdater(
            engine=engine,
            filesystem=self.filesystem,
        )

        summary = updater.update(
            sources,
            resources,
            target_directory=target,
            replace=replace,
        )

        self._report(
            summary,
        )

        changes = self._changes(
            summary,
        )

        errors = [
            {
                "kind": error.kind,
                "name": error.name,
                "path": str(error.path),
                "key": error.key,
                "message": error.message,
            }
            for error in summary.errors
        ]

        self.outputs.update(
            {
                "success": not summary.failed,
                "failed": summary.failed,
                "resources_processed": summary.resources_processed,
                "resources_succeeded": summary.resources_succeeded,
                "resources_failed": summary.resources_failed,
                "changes": summary.changes_count,
                "errors": errors,
            },
        )

        return PluginResult(
            success=not summary.failed,
            changed=summary.changes_count > 0,
            outputs=dict(self.outputs),
            changes=changes,
            errors=errors,
            metadata=self._metadata(),
        )

    # ------------------------------------------------------------------
    # Deployment mode
    # ------------------------------------------------------------------

    def _execute_deployments(self) -> PluginResult:
        """
        Apply ConfigMap/Secret sources from release context.

        A deployment resource may represent either:

        - an entropy ConfigMapSecretUpdate definition, identified by
          the presence of ``operations``; or
        - a native ConfigMap/Secret resource, identified by the
          absence of ``operations``.

        Native resources are merged into existing targets unless
        ``replace`` is enabled.
        """

        configmaps = self.arguments.get(
            "configmaps",
            [],
        )

        secrets = self.arguments.get(
            "secrets",
            [],
        )

        if not isinstance(
            configmaps,
            list,
        ):
            raise ConfigMapSecretUpdateException(
                "Argument 'configmaps' must be a list.",
            )

        if not isinstance(
            secrets,
            list,
        ):
            raise ConfigMapSecretUpdateException(
                "Argument 'secrets' must be a list.",
            )

        resources = [
            *configmaps,
            *secrets,
        ]

        if not resources:

            self.message.info(
                "No ConfigMap/Secret resources require updates.",
            )

            return PluginResult(
                success=True,
                changed=False,
                outputs={
                    "resources_processed": 0,
                    "resources_succeeded": 0,
                    "resources_failed": 0,
                    "changes": 0,
                    "errors": [],
                },
                errors=[],
                metadata=self._metadata(),
            )

        replace = self.arguments.boolean(
            "replace",
            False,
        )

        if replace is None:
            replace = False

        engine = ConfigMapSecretUpdateEngine(
            yaml_loader=self._parse_yaml,
            yaml_dumper=self._serialize_yaml,
        )

        processed = 0
        succeeded = 0
        changes = 0

        detailed_changes: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for resource in resources:

            processed += 1

            try:

                self._validate_deployment_resource(
                    resource,
                )

                target_path = self.filesystem.path(
                    resource["repository"],
                )

                source_path = self.filesystem.path(
                    resource["source"],
                )

                target_resource = None

                if self.filesystem.exists(target_path):

                    target_loader = ConfigMapSecretTargetLoader(
                        filesystem=self.filesystem,
                    )

                    target_resources = target_loader.load_file(
                        target_path,
                    )

                    target_resource = next(
                        (
                            item
                            for item in target_resources
                            if (item.kind == resource["kind"] and item.name == resource["name"])
                        ),
                        None,
                    )

                source_documents = self._load_source_documents(
                    source_path,
                )

                source_document = self._find_source_document(
                    source_documents,
                    kind=resource["kind"],
                    name=resource["name"],
                )

                if source_document is None:
                    raise ConfigMapSecretUpdateException(
                        f"Source resource "
                        f"'{resource['kind']}/{resource['name']}' "
                        f"not found in '{source_path}'.",
                    )

                source = self._build_source(
                    resource,
                    source_document,
                )

                # ------------------------------------------------------
                # Existing target
                # ------------------------------------------------------

                if target_resource is not None:

                    if source.source_type == SourceType.UPDATE:

                        assert source.update is not None

                        resource_changes = engine.apply(
                            target_resource.document,
                            source.update,
                            replace=replace,
                        )

                    else:

                        assert source.resource is not None

                        resource_changes = self._apply_native_resource(
                            target_resource.document,
                            source.resource.document,
                            replace=replace,
                        )

                    for change in resource_changes:

                        detailed_changes.append(
                            {
                                "kind": resource["kind"],
                                "name": resource["name"],
                                "path": str(target_path),
                                **change,
                            },
                        )

                    self._write_target_file(
                        target_resource.target_file,
                    )

                    changes += len(
                        resource_changes,
                    )

                    succeeded += 1

                    self.message.info(
                        f"Updated " f"{resource['kind']}/" f"{resource['name']}.",
                    )

                    continue

                # ------------------------------------------------------
                # Missing target
                # ------------------------------------------------------

                created_document = self._create_source_document(
                    source,
                )

                self._write_new_target(
                    target_path,
                    created_document,
                )

                change = {
                    "action": "create",
                    "key": "*",
                    "status": "created",
                }

                detailed_changes.append(
                    {
                        "kind": resource["kind"],
                        "name": resource["name"],
                        "path": str(target_path),
                        **change,
                    },
                )

                changes += 1
                succeeded += 1

                self.message.info(
                    f"Created " f"{resource['kind']}/" f"{resource['name']}.",
                )

            except Exception as exc:

                # traceback.print_exc()

                errors.append(
                    {
                        "kind": resource.get(
                            "kind",
                            "",
                        ),
                        "name": resource.get(
                            "name",
                            "",
                        ),
                        "path": resource.get(
                            "repository",
                            "",
                        ),
                        "message": str(exc),
                    },
                )

        self.outputs.update(
            {
                "success": not errors,
                "resources_processed": processed,
                "resources_succeeded": succeeded,
                "resources_failed": len(errors),
                "changes": changes,
                "errors": errors,
            },
        )

        return PluginResult(
            success=not errors,
            changed=changes > 0,
            outputs=dict(
                self.outputs,
            ),
            changes=detailed_changes,
            errors=errors,
            metadata=self._metadata(),
        )

    # ------------------------------------------------------------------
    # Deployment source handling
    # ------------------------------------------------------------------

    def _validate_deployment_resource(
        self,
        resource: Any,
    ) -> None:
        """
        Validate one deployment resource mapping.

        ``operations`` is optional because native ConfigMap/Secret
        resources do not contain operations.
        """

        if not isinstance(
            resource,
            dict,
        ):
            raise ConfigMapSecretUpdateException(
                "Deployment resource must be an object.",
            )

        for field in (
            "kind",
            "name",
            "source",
            "repository",
        ):

            value = resource.get(
                field,
            )

            if value is None:
                raise ConfigMapSecretUpdateException(
                    f"Deployment resource requires '{field}'.",
                )

        if resource["kind"] not in {
            "ConfigMap",
            "Secret",
        }:
            raise ConfigMapSecretUpdateException(
                f"Unsupported deployment resource kind " f"'{resource['kind']}'.",
            )

        if "operations" in resource and not isinstance(
            resource["operations"],
            list,
        ):
            raise ConfigMapSecretUpdateException(
                "Deployment resource 'operations' " "must be a list.",
            )

    def _build_source(
        self,
        resource: dict[str, Any],
        document: dict[str, Any] | None,
    ) -> ConfigMapSecretSource:
        """
        Build a typed source from a deployment resource.

        Resources containing ``operations`` are treated as
        entropy update definitions.

        Resources without ``operations`` are treated as native
        ConfigMap/Secret resources.
        """

        document_kind = document.get("kind")

        if document_kind == "ConfigMapSecretUpdate":

            operations = document.get(
                "operations",
                [],
            )

            if not isinstance(
                operations,
                list,
            ):
                raise ConfigMapSecretUpdateException(
                    "ConfigMapSecretUpdate 'operations' must be a list.",
                )

            parsed_operations = [
                UpdateOperation(
                    action=operation["action"],
                    key=operation["key"],
                    value=operation.get("value"),
                    format=operation.get("format"),
                    entries=operation.get("entries"),
                )
                for operation in operations
            ]

            definition = ConfigMapSecretUpdate(
                api_version="entropy/v1",
                kind="ConfigMapSecretUpdate",
                target=UpdateTarget(
                    kind=resource["kind"],
                    name=resource["name"],
                ),
                operations=parsed_operations,
            )

            return ConfigMapSecretSource(
                source_type=SourceType.UPDATE,
                path=self.filesystem.path(
                    resource["source"],
                ),
                update=definition,
            )

        if document is None:

            raise ConfigMapSecretUpdateException(
                f"Native source document is required for "
                f"'{resource['kind']}/{resource['name']}'.",
            )

        native_resource = ConfigMapSecretResource(
            api_version=document.get(
                "apiVersion",
                "v1",
            ),
            kind=document["kind"],
            name=document["metadata"]["name"],
            document=document,
        )

        return ConfigMapSecretSource(
            source_type=SourceType.RESOURCE,
            path=self.filesystem.path(
                resource["source"],
            ),
            resource=native_resource,
        )

    def _load_source_documents(
        self,
        path: Path,
    ) -> list[Any]:
        """
        Load all YAML documents from a source file.
        """

        if not self.filesystem.exists(path):
            raise ConfigMapSecretUpdateException(
                f"Source YAML file '{path}' does not exist.",
            )

        if not self.filesystem.is_file(path):
            raise ConfigMapSecretUpdateException(
                f"Source YAML path '{path}' is not a file.",
            )

        try:

            content = self.filesystem.read_text(
                path,
            )

            documents = self.filesystem.load_yaml_documents(
                content,
            )

        except Exception as exc:

            raise ConfigMapSecretUpdateException(
                f"Unable to read source YAML file " f"'{path}': {exc}",
            ) from exc

        if documents is None:
            return []

        if not isinstance(
            documents,
            list,
        ):
            return [
                documents,
            ]

        return documents

    @staticmethod
    def _find_source_document(
        documents: list[Any],
        *,
        kind: str,
        name: str,
    ) -> dict[str, Any] | None:
        """
        Find a ConfigMap/Secret source definition.

        Supports both:

        - Native ConfigMap/Secret resources.
        - Entropy ConfigMapSecretUpdate definitions targeting
        a ConfigMap/Secret.
        """

        for document in documents:

            if not isinstance(
                document,
                dict,
            ):
                continue

            document_kind = document.get(
                "kind",
            )

            #
            # Native ConfigMap / Secret
            #

            if document_kind == kind:

                metadata = document.get(
                    "metadata",
                )

                if not isinstance(
                    metadata,
                    dict,
                ):
                    continue

                if metadata.get("name") == name:

                    return document

            #
            # Entropy ConfigMapSecretUpdate
            #

            if document_kind == "ConfigMapSecretUpdate":

                target = document.get(
                    "target",
                )

                if not isinstance(
                    target,
                    dict,
                ):
                    continue

                if target.get("kind") == kind and target.get("name") == name:

                    return document

        return None

    @staticmethod
    def _apply_native_resource(
        target: dict[str, Any],
        source: dict[str, Any],
        *,
        replace: bool,
    ) -> list[dict[str, Any]]:
        """
        Merge or replace a native ConfigMap/Secret resource.

        With replace=False, only source fields are changed and
        destination-only data keys are preserved.

        With replace=True, the complete resource is replaced.
        """

        if replace:

            target.clear()
            target.update(
                source,
            )

            return [
                {
                    "action": "replace",
                    "key": "*",
                    "status": "replaced_resource",
                },
            ]

        source_data = source.get(
            "data",
            {},
        )

        if source_data is None:
            source_data = {}

        if not isinstance(
            source_data,
            dict,
        ):
            raise ConfigMapSecretUpdateException(
                "Native ConfigMap/Secret 'data' must be an object.",
            )

        target_data = target.get(
            "data",
        )

        if target_data is None:
            target_data = {}
            target["data"] = target_data

        if not isinstance(
            target_data,
            dict,
        ):
            raise ConfigMapSecretUpdateException(
                "Target ConfigMap/Secret 'data' must be an object.",
            )

        changes: list[dict[str, Any]] = []

        for key, value in source_data.items():

            if key in target_data:

                target_data[key] = value

                changes.append(
                    {
                        "action": "update",
                        "key": key,
                        "status": "updated_existing",
                    },
                )

            else:

                target_data[key] = value

                changes.append(
                    {
                        "action": "add",
                        "key": key,
                        "status": "added_missing",
                    },
                )

        return changes

    @staticmethod
    def _create_source_document(
        source: ConfigMapSecretSource,
    ) -> dict[str, Any]:
        """
        Return the complete native resource for creation.
        """

        if source.source_type == SourceType.RESOURCE:

            assert source.resource is not None

            return dict(
                source.resource.document,
            )

        raise ConfigMapSecretUpdateException(
            "Creating a missing ConfigMap/Secret from an "
            "update definition requires the update source "
            "to be resolved separately.",
        )

    def _write_new_target(
        self,
        path: Path,
        document: dict[str, Any],
    ) -> None:
        """
        Write a newly created native resource.
        """

        content = self._serialize_yaml(
            document,
        ).rstrip()

        self.filesystem.write_text(
            path,
            content + "\n",
        )

    # ------------------------------------------------------------------
    # General helpers
    # ------------------------------------------------------------------

    def _required_path(
        self,
        name: str,
    ) -> Path:
        """
        Return a required plugin path argument.
        """

        value = self.arguments.string(
            name,
        )

        if value is None or not value.strip():
            raise ConfigMapSecretUpdateException(
                f"Argument '{name}' must be a non-empty path.",
            )

        return self.filesystem.path(
            value,
        )

    def _validate_directories(
        self,
        source: Path,
        target: Path,
    ) -> None:
        """
        Validate source and target directories.
        """

        if not self.filesystem.exists(source):
            raise ConfigMapSecretUpdateException(
                f"Source directory '{source}' does not exist.",
            )

        if not self.filesystem.is_directory(source):
            raise ConfigMapSecretUpdateException(
                f"Source path '{source}' is not a directory.",
            )

        if not self.filesystem.exists(target):
            self.filesystem.mkdir(target)

        elif not self.filesystem.is_directory(target):
            raise ConfigMapSecretUpdateException(
                f"Target path '{target}' is not a directory.",
            )

    def _parse_yaml(
        self,
        content: str,
    ) -> Any:
        """Parse one YAML document."""

        return self.filesystem.parse_yaml(
            content,
        )

    def _serialize_yaml(
        self,
        value: Any,
    ) -> str:
        """Serialize one YAML document."""

        return self.filesystem.serialize_yaml(
            value,
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _report(
        self,
        summary,
    ) -> None:
        """Report the complete update summary."""

        self.message.info(
            "ConfigMap/Secret Update Summary",
        )

        self.message.info(
            f"Resources processed: " f"{summary.resources_processed}",
        )

        self.message.info(
            f"Resources succeeded: " f"{summary.resources_succeeded}",
        )

        self.message.info(
            f"Resources failed: " f"{summary.resources_failed}",
        )

        self.message.info(
            f"Changes applied: " f"{summary.changes_count}",
        )

        if summary.results:

            self.message.info(
                "Successful resources:",
            )

            for result in summary.results:

                action = "CREATE" if result.created else "UPDATE"

                self.message.info(
                    f"  {action:<6} " f"{result.kind}/{result.name} " f"({result.path})",
                )

                for change in result.changes:

                    action = change["action"].upper()
                    key = change["key"]
                    status = change.get(
                        "status",
                    )

                    if status == "replaced_add":

                        self.message.info(
                            f"    {action:<6} " f"{key} (replaced add)",
                        )

                    elif status == "unchanged":

                        self.message.info(
                            f"    {action:<6} " f"{key} (unchanged)",
                        )

                    else:

                        self.message.info(
                            f"    {action:<6} " f"{key}",
                        )

        if summary.errors:

            self.message.error(
                "Failed resources:",
            )

            for error in summary.errors:

                location = f"{error.kind}/{error.name}"

                if error.key:

                    self.message.error(
                        f"  {location} " f"[{error.key}]: " f"{error.message}",
                    )

                else:

                    self.message.error(
                        f"  {location}: " f"{error.message}",
                    )

    def _metadata(
        self,
    ) -> dict[str, Any]:
        """Build plugin result metadata."""

        return {
            "artifacts": {name: str(path) for name, path in self.artifacts.items()},
        }

    def _changes(
        self,
        summary,
    ) -> list[dict[str, Any]]:
        """
        Return detailed changes from all successful resources.
        """

        changes: list[dict[str, Any]] = []

        for result in summary.results:

            for change in result.changes:

                changes.append(
                    {
                        "kind": result.kind,
                        "name": result.name,
                        "path": str(result.path),
                        **change,
                    },
                )

        return changes

    def _write_target_file(
        self,
        target_file,
    ) -> None:
        """
        Write all YAML documents in an existing target file.
        """

        content = self.filesystem.serialize_yaml_documents(
            target_file.documents,
        )

        self.filesystem.write_text(
            target_file.path,
            content,
        )
