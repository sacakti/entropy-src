"""
cm_secret_update plugin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.exceptions import EntropyException
from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .engine import ConfigMapSecretUpdateEngine
from .loader import ConfigMapSecretUpdateLoader
from .target_loader import ConfigMapSecretTargetLoader
from .updater import ConfigMapSecretUpdater


class CMSecretUpdateException(EntropyException):
    """
    Base class for CMSecretUpdate
    """


class CmSecretUpdatePlugin(
    BasePlugin,
):
    """
    Update ConfigMap and Secret YAML definitions.
    """

    def execute(
        self,
    ) -> None:
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

        except Exception:

            # self.message.error(
            #     str(exc),
            # )

            raise

        self.message.success(
            "ConfigMap/Secret updated successfully.",
        )

        return result

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> None:
        """
        Execute ConfigMap/Secret updates.
        """

        source = self._required_path(
            "source",
        )

        target = self._required_path(
            "target",
        )

        replace = self._replace()

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

        #
        # Source definitions.
        #

        source_loader = ConfigMapSecretUpdateLoader(
            filesystem=self.filesystem,
        )

        definitions = source_loader.load_directory(
            source,
        )

        self.message.info(
            f"Loaded {len(definitions)} " f"update definition(s).",
        )

        #
        # Target resources.
        #

        target_loader = ConfigMapSecretTargetLoader(
            filesystem=self.filesystem,
        )

        resources = target_loader.load_directory(
            target,
        )

        self.message.info(
            f"Loaded {len(resources)} " f"target resource(s).",
        )

        #
        # Engine.
        #

        engine = ConfigMapSecretUpdateEngine(
            yaml_loader=self._parse_yaml,
            yaml_dumper=self._serialize_yaml,
        )

        #
        # Updater.
        #

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

        self._report(
            summary,
        )

        self.outputs["success"] = not summary.failed
        self.outputs["failed"] = summary.failed
        self.outputs["resources_processed"] = summary.resources_processed
        self.outputs["resources_succeeded"] = summary.resources_succeeded
        self.outputs["resources_failed"] = summary.resources_failed
        self.outputs["changes"] = summary.changes_count
        self.outputs["errors"] = [
            {
                "kind": error.kind,
                "name": error.name,
                "path": str(error.path),
                "key": error.key,
                "message": error.message,
            }
            for error in summary.errors
        ]

        # if summary.failed:

        #     raise CMSecretUpdateException(
        #         "One or more ConfigMap/Secret updates failed.",
        #     )

        return PluginResult(
            success=False,
            changed=summary.changes_count > 0,
            outputs=dict(self.outputs),
            errors=[
                {
                    "kind": error.kind,
                    "name": error.name,
                    "path": str(error.path),
                    "key": error.key,
                    "message": error.message,
                }
                for error in summary.errors
            ],
            metadata={
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )

    # ------------------------------------------------------------------
    # Arguments
    # ------------------------------------------------------------------

    def _required_path(
        self,
        name: str,
    ) -> Path:
        """
        Return a required plugin path argument.
        """

        value = self.arguments.get(
            name,
        )

        if (
            not isinstance(
                value,
                str,
            )
            or not value.strip()
        ):

            raise CMSecretUpdateException(
                f"Argument '{name}' must be a " "non-empty path.",
            )

        return self.filesystem.path(
            value,
        )

    def _replace(
        self,
    ) -> bool:
        """
        Return the replace-existing option.
        """

        value = self.arguments.boolean(
            "replace",
            False,
        )

        assert value is not None

        return value

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_directories(
        self,
        source: Path,
        target: Path,
    ) -> None:
        """
        Validate source and target directories.
        """

        if not self.filesystem.exists(
            source,
        ):

            raise FileNotFoundError(
                f"Source directory '{source}' does not exist.",
            )

        if not self.filesystem.is_directory(
            source,
        ):

            raise CMSecretUpdateException(
                f"Source path '{source}' is not a directory.",
            )

        if not self.filesystem.exists(
            target,
        ):

            self.filesystem.mkdir(
                target,
            )

        elif not self.filesystem.is_directory(
            target,
        ):

            raise CMSecretUpdateException(
                f"Target path '{target}' is not a directory.",
            )

    # ------------------------------------------------------------------
    # YAML
    # ------------------------------------------------------------------

    def _parse_yaml(
        self,
        content: str,
    ) -> Any:
        """
        Parse one YAML document.
        """

        return self.filesystem.parse_yaml(
            content,
        )

    def _serialize_yaml(
        self,
        value: Any,
    ) -> str:
        """
        Serialize one YAML document.
        """

        return self.filesystem.serialize_yaml(
            value,
        )

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _report(
        self,
        summary,
    ) -> None:
        """
        Report the complete update summary.
        """

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
                    f"  {action:<6} " f"{result.kind}/" f"{result.name} " f"({result.path})",
                )

                for change in result.changes:

                    action = change["action"].upper()
                    key = change["key"]
                    status = change.get(
                        "status",
                    )

                    if status == "replaced_add":

                        self.message.info(
                            f"    " f"{action:<6} " f"{key} " f"(replaced add)",
                        )

                    elif status == "unchanged":

                        self.message.info(
                            f"    " f"{action:<6} " f"{key} " f"(unchanged)",
                        )

                    else:

                        self.message.info(
                            f"    " f"{action:<6} " f"{key}",
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
