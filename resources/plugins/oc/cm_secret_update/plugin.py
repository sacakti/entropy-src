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

    def _execute(self) -> PluginResult:
        """
        Execute ConfigMap/Secret updates.
        """

        source = self._required_path("source")
        target = self._required_path("target")
        replace = self.arguments.boolean("replace", False)

        if replace is None:
            replace = False

        self._validate_directories(source, target)

        self.message.info(f"Source: {source}")
        self.message.info(f"Target: {target}")
        self.message.info(
            f"Replace existing: {str(replace).lower()}",
        )

        source_loader = ConfigMapSecretUpdateLoader(
            filesystem=self.filesystem,
        )

        definitions = source_loader.load_directory(source)

        self.message.info(
            f"Loaded {len(definitions)} update definition(s).",
        )

        target_loader = ConfigMapSecretTargetLoader(
            filesystem=self.filesystem,
        )

        resources = target_loader.load_directory(target)

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
            definitions,
            resources,
            target_directory=target,
            replace=replace,
        )

        self._report(summary)

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
            errors=errors,
            metadata=self._metadata(),
        )

    def _required_path(self, name: str) -> Path:
        """
        Return a required plugin path argument.
        """

        value = self.arguments.string(name)

        if value is None or not value.strip():
            raise ConfigMapSecretUpdateException(
                f"Argument '{name}' must be a non-empty path.",
            )

        return self.filesystem.path(value)

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

    def _parse_yaml(self, content: str) -> Any:
        """Parse one YAML document."""

        return self.filesystem.parse_yaml(content)

    def _serialize_yaml(self, value: Any) -> str:
        """Serialize one YAML document."""

        return self.filesystem.serialize_yaml(value)

    def _report(self, summary) -> None:
        """Report the complete update summary."""

        self.message.info("ConfigMap/Secret Update Summary")
        self.message.info(
            f"Resources processed: {summary.resources_processed}",
        )
        self.message.info(
            f"Resources succeeded: {summary.resources_succeeded}",
        )
        self.message.info(
            f"Resources failed: {summary.resources_failed}",
        )
        self.message.info(
            f"Changes applied: {summary.changes_count}",
        )

        if summary.results:
            self.message.info("Successful resources:")

            for result in summary.results:
                action = "CREATE" if result.created else "UPDATE"

                self.message.info(
                    f"  {action:<6} "
                    f"{result.kind}/{result.name} "
                    f"({result.path})",
                )

                for change in result.changes:
                    action = change["action"].upper()
                    key = change["key"]
                    status = change.get("status")

                    if status == "replaced_add":
                        self.message.info(
                            f"    {action:<6} "
                            f"{key} (replaced add)",
                        )

                    elif status == "unchanged":
                        self.message.info(
                            f"    {action:<6} "
                            f"{key} (unchanged)",
                        )

                    else:
                        self.message.info(
                            f"    {action:<6} {key}",
                        )

        if summary.errors:
            self.message.error("Failed resources:")

            for error in summary.errors:
                location = f"{error.kind}/{error.name}"

                if error.key:
                    self.message.error(
                        f"  {location} "
                        f"[{error.key}]: {error.message}",
                    )
                else:
                    self.message.error(
                        f"  {location}: {error.message}",
                    )

    def _metadata(self) -> dict[str, Any]:
        """Build plugin result metadata."""

        return {
            "artifacts": {
                name: str(path)
                for name, path in self.artifacts.items()
            },
        }
