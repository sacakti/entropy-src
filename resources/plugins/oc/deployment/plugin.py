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
                    1 for change in resource_changes if change.get("status") != "unchanged"
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

        if not isinstance(resources, list):
            raise DeploymentPluginException(
                "Argument 'deployments' must be a list.",
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

                action = resource["action"].strip().upper()

                # ---------------------------------------------------------
                # CREATE
                # repository is the complete target YAML path.
                # ---------------------------------------------------------
                if action == "CREATE":
                    target_path = self.filesystem.path(
                        resource["repository"].strip(),
                    )

                    self._create_deployment(
                        resource=resource,
                        target_path=target_path,
                    )

                    changes += 1
                    succeeded += 1

                    self.message.info(
                        f"Created Deployment/{resource['name']}.",
                    )

                    continue

                # ---------------------------------------------------------
                # UPDATE
                # repository is the repository directory.
                # file is the target YAML filename.
                # ---------------------------------------------------------
                repository_path = self.filesystem.path(
                    resource["repository"].strip(),
                )

                if not self.filesystem.exists(repository_path):
                    raise DeploymentPluginException(
                        f"Deployment repository " f"'{repository_path}' does not exist.",
                    )

                if not self.filesystem.is_directory(repository_path):
                    raise DeploymentPluginException(
                        f"Deployment repository " f"'{repository_path}' is not a directory.",
                    )

                path = repository_path / resource["file"]

                targets = target_loader.load_file(path)

                target = next(
                    (item for item in targets if item.name == resource["name"]),
                    None,
                )

                if target is None:
                    raise DeploymentPluginException(
                        f"Target Deployment '{resource['name']}' " f"not found in '{path}'.",
                    )

                definition = build_context_definition(resource)

                resource_changes = engine.apply(
                    target.document,
                    definition,
                    target_image=resource["target_image"],
                )

                self._write_target_file(target.target_file)

                resource_change_count = sum(
                    1 for change in resource_changes if change.get("status") != "unchanged"
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
                        "path": resource.get(
                            "file",
                            resource.get("source", ""),
                        ),
                        "message": str(exc),
                    },
                )

        return self._result(
            processed,
            succeeded,
            changes,
            errors,
        )

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
            raise DeploymentPluginException(
                "Deployment resource must be an object.",
            )

        for key in ("name", "kind", "action"):
            value = resource.get(key)

            if not isinstance(value, str) or not value.strip():
                raise DeploymentPluginException(
                    f"Deployment resource requires '{key}'.",
                )

        action = resource["action"].strip().upper()

        if action == "CREATE":
            for key in ("source", "repository"):
                value = resource.get(key)

                if not isinstance(value, str) or not value.strip():
                    raise DeploymentPluginException(
                        f"Deployment CREATE resource requires '{key}'.",
                    )

            return

        if action == "UPDATE":
            for key in (
                "file",
                "repository",
                "container",
                "target_image",
            ):
                value = resource.get(key)

                if not isinstance(value, str) or not value.strip():
                    raise DeploymentPluginException(
                        f"Deployment UPDATE resource requires '{key}'.",
                    )

            return

        raise DeploymentPluginException(
            f"Unsupported Deployment action '{resource['action']}'.",
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
            "artifacts": {name: str(path) for name, path in self.artifacts.items()},
        }

    def _create_deployment(
        self,
        resource: dict[str, Any],
        target_path: Path,
    ) -> None:
        source = resource["source"]
        name = resource["name"]

        source_path = self.filesystem.path(source)

        if not source_path.exists():
            raise DeploymentPluginException(f"Deployment source does not exist: {source}")

        if not source_path.is_file():
            raise DeploymentPluginException(f"Deployment source is not a file: {source}")

        if target_path.exists():
            raise DeploymentPluginException(f"Deployment target already exists: {target_path}")

        document = self.filesystem.read_yaml(source_path)

        if not isinstance(document, dict):
            raise DeploymentPluginException(f"Invalid Deployment YAML: {source}")

        if document.get("kind") != "Deployment":
            raise DeploymentPluginException(
                f"Expected Deployment resource in {source}, " f"found {document.get('kind')!r}"
            )

        metadata = document.get("metadata")

        if not isinstance(metadata, dict):
            raise DeploymentPluginException(f"Deployment metadata is missing in {source}")

        source_name = metadata.get("name")

        if source_name != name:
            raise DeploymentPluginException(
                f"Deployment name mismatch: context={name!r}, " f"source={source_name!r}"
            )

        self._apply_create_image(document, resource)

        target_path.parent.mkdir(parents=True, exist_ok=True)

        self.filesystem.write_yaml(target_path, document)

    def _apply_create_image(
        self,
        document: dict[str, Any],
        resource: dict[str, Any],
    ) -> None:
        container = resource.get("container")
        target_image = resource.get("target_image")

        # A normal CREATE without Docker/image correlation is valid.
        if container is None and target_image is None:
            return

        # Image metadata must always be supplied as a pair.
        if not container or not target_image:
            raise DeploymentPluginException(
                "Deployment CREATE requires both 'container' "
                "and 'target_image' when image metadata is provided."
            )

        spec = document.get("spec")

        if not isinstance(spec, dict):
            raise DeploymentPluginException("Deployment spec is missing.")

        template = spec.get("template")

        if not isinstance(template, dict):
            raise DeploymentPluginException("Deployment spec.template is missing.")

        pod_spec = template.get("spec")

        if not isinstance(pod_spec, dict):
            raise DeploymentPluginException("Deployment spec.template.spec is missing.")

        containers = pod_spec.get("containers")

        if not isinstance(containers, list):
            raise DeploymentPluginException("Deployment spec.template.spec.containers is missing.")

        for item in containers:
            if not isinstance(item, dict):
                continue

            if item.get("name") == container:
                item["image"] = target_image
                return

        raise DeploymentPluginException(
            f"Container {container!r} was not found in " f"Deployment {resource.get('name')!r}."
        )

    @staticmethod
    def _resource_repository(resource: dict[str, Any]) -> str:
        value = resource.get("repository")

        if not isinstance(value, str) or not value.strip():
            raise DeploymentPluginException(
                "Deployment resource requires 'repository'.",
            )

        return value.strip()
