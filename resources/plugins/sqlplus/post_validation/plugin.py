"""
Post-deployment SQLPlus validation plugin.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import PostValidationPluginException
from .validator import PostValidationValidator


class PostValidationPlugin(BasePlugin):
    """
    Validate a SQLPlus deployment against pre-validation expectations.
    """

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute post-deployment validation.
        """

        self.message.info(
            "Starting post-validation.",
        )

        with self.activity(
            "post_validation",
        ):
            changes, errors, warnings = self._execute()

        success = not errors

        if success:
            self.message.success(
                "Post-validation completed successfully.",
            )
        else:
            self.message.error(
                "Post-validation detected deployment failures.",
            )

        return PluginResult(
            success=success,
            changed=bool(
                self.outputs.get(
                    "dashboard",
                ),
            ),
            outputs=dict(
                self.outputs,
            ),
            changes=changes,
            errors=errors,
            warnings=warnings,
            metadata={
                "artifacts": {
                    name: str(path)
                    for name, path in self.artifacts.items()
                },
            },
        )

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """
        Resolve configuration and execute post-deployment validation.
        """

        base = self.arguments.path(
            "path",
        )

        if base is None:
            raise PostValidationPluginException(
                "'path' is required.",
            )

        base = base.resolve()

        if not base.exists():
            raise PostValidationPluginException(
                f"Validation path does not exist: {base}",
            )

        if not base.is_dir():
            raise PostValidationPluginException(
                f"Validation path is not a directory: {base}",
            )

        json_path = self._resolve_json(
            base,
        )

        log_path = self._resolve_log(
            base,
            json_path,
        )

        output_path = self._resolve_output(
            base,
            json_path,
        )

        embed_log = self.arguments.boolean(
            "embed_log",
            True,
        )

        self.message.info(
            f"Pre-validation : {json_path}",
        )

        self.message.info(
            f"Deployment log : {log_path}",
        )

        self.message.info(
            f"Dashboard      : {output_path}",
        )

        validator = PostValidationValidator()

        validation = validator.validate(
            json_path=json_path,
            log_path=log_path,
        )

        dashboard = validator.build_dashboard(
            result=validation,
            output=output_path,
            embed_log=embed_log,
        )

        self.artifacts[
            "post_validation_dashboard"
        ] = dashboard

        changes = [
            {
                "action": "post_validation",
                "status": "completed",
                "release": validation.release,
                "dashboard": str(dashboard),
            },
        ]

        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        for associate in validation.associates:

            item = {
                "associate": associate.name,
                "status": associate.status,
                "errors": len(
                    associate.errors,
                ),
                "mismatches": len(
                    associate.mismatches,
                ),
                "notrun_files": associate.not_run_files,
            }

            if associate.status == "fail":
                errors.append(
                    item,
                )

            elif associate.status in {
                "partial",
                "notrun",
            }:
                warnings.append(
                    item,
                )

        self.outputs.update(
            {
                "success": not errors,
                "release": validation.release,
                "dashboard": str(dashboard),
                "associates": len(
                    validation.associates,
                ),
                "passed": validation.passed,
                "failed": validation.failed,
                "partial": validation.partial,
                "notrun": validation.notrun,
                "error_lines": validation.error_lines,
                "count_mismatches": validation.count_mismatches,
                "results": [
                    self._serialize_associate(
                        associate,
                    )
                    for associate in validation.associates
                ],
            },
        )

        return (
            changes,
            errors,
            warnings,
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _resolve_json(
        self,
        base: Path,
    ) -> Path:
        """
        Resolve pre_validation.json.
        """

        configured = self.arguments.path(
            "json",
            None,
        )

        if configured is not None:

            configured = configured.resolve()

            if not configured.exists():
                raise PostValidationPluginException(
                    f"Pre-validation file does not exist: "
                    f"{configured}",
                )

            if not configured.is_file():
                raise PostValidationPluginException(
                    f"Pre-validation path is not a file: "
                    f"{configured}",
                )

            return configured

        matches = sorted(
            (
                path
                for path in base.rglob(
                    "pre_validation.json",
                )
                if path.is_file()
            ),
            key=lambda path: str(path).casefold(),
        )

        if not matches:
            raise PostValidationPluginException(
                f"'pre_validation.json' was not found under: "
                f"{base}",
            )

        if len(matches) > 1:
            raise PostValidationPluginException(
                "Multiple 'pre_validation.json' files were found. "
                "Specify the 'json' argument explicitly.",
            )

        return matches[0].resolve()

    def _resolve_log(
        self,
        base: Path,
        json_path: Path,
    ) -> Path:
        """
        Resolve the deployment log.
        """

        configured = self.arguments.path(
            "log",
            None,
        )

        if configured is not None:

            configured = configured.resolve()

            if not configured.exists():
                raise PostValidationPluginException(
                    f"Deployment log does not exist: "
                    f"{configured}",
                )

            if not configured.is_file():
                raise PostValidationPluginException(
                    f"Deployment log path is not a file: "
                    f"{configured}",
                )

            return configured

        release = self._read_release(
            json_path,
        )

        logs = [
            path
            for path in base.rglob("*")
            if path.is_file()
            and path.suffix.casefold() == ".log"
        ]

        if not logs:
            raise PostValidationPluginException(
                f"No deployment log found under: {base}",
            )

        if release:

            tagged = [
                path
                for path in logs
                if release.casefold()
                in path.name.casefold()
            ]

            if tagged:
                logs = tagged

        return max(
            logs,
            key=lambda path: path.stat().st_mtime,
        ).resolve()

    def _resolve_output(
        self,
        base: Path,
        json_path: Path,
    ) -> Path:
        """
        Resolve dashboard output path.
        """

        configured = self.arguments.path(
            "output",
            None,
        )

        if configured is not None:
            return configured.resolve()

        release = self._read_release(
            json_path,
        )

        if not release:
            release = base.name

        safe_release = self._safe_name(
            release,
        )

        return (
            json_path.parent
            / f"{safe_release}_post_validation_dashboard.html"
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_associate(
        associate: Any,
    ) -> dict[str, Any]:
        """
        Convert a ValidationAssociateResult into workflow output data.
        """

        return {
            "display": associate.name,
            "status": associate.status,
            "errors": [
                {
                    "file": error.file,
                    "line": error.line,
                    "message": error.message,
                }
                for error in associate.errors
            ],
            "mismatches": [
                {
                    "operation": mismatch.operation,
                    "expected": mismatch.expected,
                    "actual": mismatch.actual,
                }
                for mismatch in associate.mismatches
            ],
            "n_notrun_files": associate.not_run_files,
            "blocks_expected": associate.blocks_expected,
            "blocks_completed": associate.blocks_completed,
            "success_markers": associate.success_markers,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_release(
        json_path: Path,
    ) -> str | None:
        """
        Read the release identifier from pre_validation.json.
        """

        try:
            data = json.loads(
                json_path.read_text(
                    encoding="utf-8",
                ),
            )
        except (
            OSError,
            ValueError,
        ) as exc:
            raise PostValidationPluginException(
                "Unable to read pre-validation file: "
                f"{json_path}: {exc}",
            ) from exc

        release = data.get(
            "release",
        )

        if release is None:
            return None

        return str(
            release,
        ).strip() or None

    @staticmethod
    def _safe_name(
        value: str,
    ) -> str:
        """
        Make a value safe for use in a filename.
        """

        value = re.sub(
            r"[^A-Za-z0-9._-]+",
            "_",
            value,
        )

        return value.strip(
            "_",
        ) or "release"
