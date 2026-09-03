"""
Services and Routes plugin.
"""

from __future__ import annotations

from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import ServicesRoutesPluginException


class ServicesRoutesPlugin(
    BasePlugin,
):
    """
    Create OpenShift Service and Route YAML resources.

    This plugin currently supports CREATE only.

    Resource files are created in the repository from the
    supplied source YAML files. Cluster operations such as
    apply, replace, and delete are handled by the generic
    OpenShift plugin.
    """

    _SUPPORTED_KINDS = {
        "Service",
        "Route",
    }

    _SUPPORTED_ACTIONS = {
        "CREATE",
    }

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the plugin.
        """

        self.message.info(
            "Starting services_routes.",
        )

        try:
            with self.activity(
                "services_routes",
            ):
                result = self._execute()

        except ServicesRoutesPluginException as exc:
            self.message.error(str(exc))

            return PluginResult(
                success=False,
                changed=False,
                outputs=dict(self.outputs),
                changes=[],
                errors=[
                    {
                        "message": str(exc),
                    },
                ],
                warnings=[],
                metadata=self._metadata(),
            )

        except Exception as exc:
            self.message.error(str(exc))

            return PluginResult(
                success=False,
                changed=False,
                outputs=dict(self.outputs),
                changes=[],
                errors=[
                    {
                        "message": str(exc),
                    },
                ],
                warnings=[],
                metadata=self._metadata(),
            )

        if not result.success:
            return result

        self.message.success(
            "services_routes completed successfully.",
        )

        return result

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:
        """
        Create Service and Route YAML resources.
        """

        resources = self.arguments.get(
            "resources",
            [],
        )

        if not isinstance(resources, list):
            raise ServicesRoutesPluginException(
                "Argument 'resources' must be a list.",
            )

        if not resources:
            self.message.info(
                "No Service or Route resources require creation.",
            )

            return self._result(
                processed=0,
                succeeded=0,
                changes=0,
                errors=[],
            )

        processed = 0
        succeeded = 0
        changes = 0
        errors: list[dict[str, Any]] = []

        for resource in resources:
            processed += 1

            try:
                self._validate_resource(
                    resource,
                )

                self._create_resource(
                    resource,
                )

                succeeded += 1
                changes += 1

                self.message.info(
                    f"Created "
                    f"{resource['kind']}/{resource['name']}.",
                )

            except Exception as exc:
                errors.append(
                    {
                        "kind": (
                            resource.get("kind", "")
                            if isinstance(resource, dict)
                            else ""
                        ),
                        "name": (
                            resource.get("name", "")
                            if isinstance(resource, dict)
                            else ""
                        ),
                        "path": (
                            resource.get(
                                "source",
                                "",
                            )
                            if isinstance(resource, dict)
                            else ""
                        ),
                        "message": str(exc),
                    },
                )

        return self._result(
            processed=processed,
            succeeded=succeeded,
            changes=changes,
            errors=errors,
        )

    def _create_resource(
        self,
        resource: dict[str, Any],
    ) -> None:
        """
        Create a Service or Route YAML file.
        """

        source = self.filesystem.path(
            resource["source"].strip(),
        )

        target = self.filesystem.path(
            resource["repository"].strip(),
        )

        if not self.filesystem.exists(source):
            raise ServicesRoutesPluginException(
                f"{resource['kind']} source "
                f"'{source}' does not exist.",
            )

        if not self.filesystem.is_file(source):
            raise ServicesRoutesPluginException(
                f"{resource['kind']} source "
                f"'{source}' is not a file.",
            )

        if self.filesystem.exists(target):
            raise ServicesRoutesPluginException(
                f"{resource['kind']} target "
                f"'{target}' already exists.",
            )

        document = self.filesystem.read_yaml(
            source,
        )

        if not isinstance(document, dict):
            raise ServicesRoutesPluginException(
                f"{resource['kind']} source "
                f"'{source}' must contain a YAML object.",
            )

        expected_kind = resource["kind"].strip()

        if document.get("kind") != expected_kind:
            raise ServicesRoutesPluginException(
                f"{expected_kind} source '{source}' must have "
                f"kind '{expected_kind}'.",
            )

        metadata = document.get(
            "metadata",
        )

        if not isinstance(metadata, dict):
            raise ServicesRoutesPluginException(
                f"{expected_kind} source '{source}' "
                "requires metadata.",
            )

        source_name = metadata.get(
            "name",
        )

        if (
            not isinstance(source_name, str)
            or not source_name.strip()
        ):
            raise ServicesRoutesPluginException(
                f"{expected_kind} source '{source}' "
                "requires metadata.name.",
            )

        requested_name = resource["name"].strip()

        if source_name.strip() != requested_name:
            raise ServicesRoutesPluginException(
                f"{expected_kind} source '{source}' contains "
                f"metadata.name '{source_name}', expected "
                f"'{requested_name}'.",
            )

        self.filesystem.write_yaml(
            target,
            document,
        )

    @classmethod
    def _validate_resource(
        cls,
        resource: Any,
    ) -> None:
        """
        Validate a Service or Route resource.
        """

        if not isinstance(resource, dict):
            raise ServicesRoutesPluginException(
                "Service/Route resource must be an object.",
            )

        for key in (
            "name",
            "kind",
            "action",
            "source",
            "repository",
        ):
            value = resource.get(key)

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ServicesRoutesPluginException(
                    f"Service/Route resource requires '{key}'.",
                )

        kind = resource["kind"].strip()

        if kind not in cls._SUPPORTED_KINDS:
            supported = ", ".join(
                sorted(cls._SUPPORTED_KINDS),
            )

            raise ServicesRoutesPluginException(
                f"Unsupported Service/Route kind '{kind}'. "
                f"Expected one of: {supported}.",
            )

        action = resource["action"].strip().upper()

        if action not in cls._SUPPORTED_ACTIONS:
            supported = ", ".join(
                sorted(cls._SUPPORTED_ACTIONS),
            )

            raise ServicesRoutesPluginException(
                f"Unsupported {kind} action '{action}'. "
                f"Expected one of: {supported}.",
            )

    def _result(
        self,
        *,
        processed: int,
        succeeded: int,
        changes: int,
        errors: list[dict[str, Any]],
    ) -> PluginResult:
        """
        Build the plugin result.
        """

        failed = len(
            errors,
        )

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
            changes=[],
            errors=errors,
            warnings=[],
            metadata=self._metadata(),
        )

    def _metadata(self) -> dict[str, Any]:
        """
        Build plugin metadata.
        """

        return {
            "artifacts": {
                name: str(path)
                for name, path in self.artifacts.items()
            },
        }
