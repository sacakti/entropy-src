"""OpenShift Deployment update plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .context import build_context_definition
from .engine import DeploymentUpdateEngine
from .exceptions import DeploymentPluginException, DeploymentUpdateException
from .loader import DeploymentUpdateLoader
from .target_loader import DeploymentTargetLoader


class DeploymentPlugin(BasePlugin):
    """Update OpenShift Deployment YAML resources."""

    def execute(self) -> PluginResult:
        self.message.info("Starting Deployment update.")

        try:
            with self.activity("deployment_updater"):
                result = self._execute()
        except DeploymentUpdateException as exc:
            self.message.error(str(exc))
            return PluginResult(
                success=False,
                changed=False,
                outputs=dict(self.outputs),
                errors=[{"message": str(exc)}],
                metadata=self._metadata(),
            )
        except Exception as exc:
            self.message.error(str(exc))
            return PluginResult(
                success=False,
                changed=False,
                outputs=dict(self.outputs),
                errors=[{"message": str(exc)}],
                metadata=self._metadata(),
            )

        if not result.success:
            return result

        self.message.success("Deployment updated successfully.")
        return result

    def _execute(self) -> PluginResult:
        mode = self.arguments.string("mode", default="folder") or "folder"
        mode = mode.strip().lower()

        if mode == "folder":
            return self._execute_folder()
        if mode == "deployments":
            return self._execute_deployments()

        raise DeploymentPluginException(
            f"Unsupported mode '{mode}'. Expected 'folder' or 'deployments'.",
        )

    def _execute_folder(self) -> PluginResult:
        source = self._required_path("source")
        target = self._required_path("target")

        if not self.filesystem.exists(source):
            raise DeploymentPluginException(
                f"Source directory '{source}' does not exist.",
            )
        if not self.filesystem.is_directory(source):
            raise DeploymentPluginException(
                f"Source path '{source}' is not a directory.",
            )
        if not self.filesystem.exists(target):
            raise DeploymentPluginException(
                f"Target directory '{target}' does not exist.",
            )
        if not self.filesystem.is_directory(target):
            raise DeploymentPluginException(
                f"Target path '{target}' is not a directory.",
            )

        definitions = DeploymentUpdateLoader(self.filesystem).load_directory(source)
        target_loader = DeploymentTargetLoader(self.filesystem)
        engine = DeploymentUpdateEngine()

        processed = 0
        succeeded = 0
        changes = 0
        errors: list[dict[str, Any]] = []

        for definition in definitions:
            processed += 1
            try:
                target = self._find_target_for_definition(
                    target,
                    target_loader,
                    definition.target.name,
                )
                resource_changes = engine.apply(
                    target.document,
                    definition,
                )
                self._write_target_file(target.target_file)
                changes += sum(
                    1
                    for change in resource_changes
                    if change.get("status") != "unchanged"
                )
                succeeded += 1
            except Exception as exc:
                errors.append(
                    {
                        "kind": "Deployment",
                        "name": definition.target.name,
                        "message": str(exc),
                    },
                )

        return self._result(processed, succeeded, changes, errors)

    def _execute_deployments(self) -> PluginResult:
        resources = self.arguments.get("deployments", [])

        self.log.info(
            f"Deployment resources received: {resources!r}",
        )

        repository = self.arguments.string("repository")

        if not isinstance(resources, list):
            raise DeploymentPluginException("Argument 'deployments' must be a list.")
        if repository is None or not repository.strip():
            raise DeploymentPluginException(
                "Argument 'repository' must be a non-empty path.",
            )

        repository_path = self.filesystem.path(repository)
        if not self.filesystem.exists(repository_path):
            raise DeploymentPluginException(
                f"Deployment repository '{repository_path}' does not exist.",
            )

        if not resources:
            self.message.info("No Deployment resources require updates.")
            return self._result(0, 0, 0, [])

        target_loader = DeploymentTargetLoader(self.filesystem)
        engine = DeploymentUpdateEngine()
        processed = 0
        succeeded = 0
        changes = 0
        errors: list[dict[str, Any]] = []

        for resource in resources:
            processed += 1
            try:
                self._validate_context_resource(resource)
                path = repository_path / resource["file"]
                targets = target_loader.load_file(path)
                target = next(
                    (
                        item for item in targets
                        if item.name == resource["name"]
                    ),
                    None,
                )
                if target is None:
                    raise DeploymentPluginException(
                        f"Target Deployment '{resource['name']}' not found in '{path}'.",
                    )

                definition = build_context_definition(resource)
                resource_changes = engine.apply(
                    target.document,
                    definition,
                    target_image=resource["target_image"],
                )
                self._write_target_file(target.target_file)

                resource_change_count = sum(
                    1
                    for change in resource_changes
                    if change.get("status") != "unchanged"
                )
                changes += resource_change_count
                succeeded += 1

                self.message.info(
                    f"Updated Deployment/{resource['name']} image to "
                    f"{resource['target_image']}.",
                )
            except Exception as exc:
                errors.append(
                    {
                        "kind": "Deployment",
                        "name": resource.get("name", ""),
                        "path": resource.get("file", ""),
                        "message": str(exc),
                    },
                )

        return self._result(processed, succeeded, changes, errors)

    @staticmethod
    def _find_target_for_definition(target, loader, name):
        matches = []
        for path in sorted(target.iterdir()):
            if path.suffix.lower() not in {".yaml", ".yml"} or not path.is_file():
                continue
            matches.extend(loader.load_file(path))
        for item in matches:
            if item.name == name:
                return item
        raise DeploymentPluginException(
            f"Target Deployment '{name}' not found in '{target}'.",
        )

    @staticmethod
    def _validate_context_resource(resource: Any) -> None:
        if not isinstance(resource, dict):
            raise DeploymentPluginException("Deployment resource must be an object.")
        for key in ("name", "file", "container", "target_image"):
            value = resource.get(key)
            if not isinstance(value, str) or not value.strip():
                raise DeploymentPluginException(
                    f"Deployment resource requires '{key}'.",
                )

    def _required_path(self, name: str) -> Path:
        value = self.arguments.string(name)
        if value is None or not value.strip():
            raise DeploymentPluginException(
                f"Argument '{name}' must be a non-empty path.",
            )
        return self.filesystem.path(value)

    def _write_target_file(self, target_file) -> None:
        documents = [
            self.filesystem.serialize_yaml(document).rstrip()
            for document in target_file.documents
            if document is not None
        ]
        self.filesystem.write_text(
            target_file.path,
            "\n---\n".join(documents) + "\n",
        )

    def _result(
        self,
        processed: int,
        succeeded: int,
        changes: int,
        errors: list[dict[str, Any]],
    ) -> PluginResult:
        failed = len(errors)
        self.outputs.update(
            {
                "success": not errors,
                "resources_processed": processed,
                "resources_succeeded": succeeded,
                "resources_failed": failed,
                "changes": changes,
                "errors": errors,
            },
        )
        return PluginResult(
            success=not errors,
            changed=changes > 0,
            outputs=dict(self.outputs),
            errors=errors,
            metadata=self._metadata(),
        )

    def _metadata(self) -> dict[str, Any]:
        return {
            "artifacts": {
                name: str(path)
                for name, path in self.artifacts.items()
            },
        }
