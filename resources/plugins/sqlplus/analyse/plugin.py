"""
Oracle SQL / SQLPlus script analysis plugin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .analyzer import AnalyseAnalyzer
from .exceptions import AnalysePluginException
from .model import AnalyseFinding
from .report import AnalyseReportBuilder
from .resolver import AnalyseResolver


class AnalysePlugin(
    BasePlugin,
):
    """
    Oracle SQL / SQLPlus script analysis plugin.
    """

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute SQL script analysis.
        """

        self.message.info(
            "Starting SQL script analysis.",
        )

        changes, errors, warnings = self._execute()

        success = not errors

        if success:
            self.message.success(
                "SQL script analysis completed successfully.",
            )
        else:
            self.message.error(
                "SQL script analysis detected policy violations.",
            )

        return PluginResult(
            success=success,
            changed=bool(
                self.outputs.get(
                    "files_scanned",
                    0,
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
        Resolve configuration and analyse application directories.
        """

        resolver = AnalyseResolver()

        root = resolver.resolve_path(
            self.arguments.get(
                "path",
            ),
        )

        extensions = resolver.resolve_extensions(
            self.arguments.get(
                "extensions",
            ),
        )

        policy = resolver.resolve_policy(
            self.arguments.get(
                "policy",
            ),
        )

        applications = self._application_directories(
            root,
        )

        if not applications:
            raise AnalysePluginException(
                f"No application directories found under: {root}",
            )

        analyzer = AnalyseAnalyzer()

        report_builder = AnalyseReportBuilder()

        changes: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        total_files = 0
        total_objects = 0
        total_findings = 0
        stopped = False

        application_results: list[dict[str, Any]] = []

        for application in applications:

            self.message.info(
                f"Analysing application: {application.name}",
            )

            result = analyzer.analyse(
                path=application,
                extensions=extensions,
                policy=policy,
            )

            report_path = self._report_path(
                application,
            )

            report_builder.build(
                result=result,
                output=report_path,
            )

            artifact_name = (
                f"analyse_{application.name}_report"
            )

            self.artifacts[artifact_name] = report_path

            total_files += result.files_scanned
            total_objects += len(
                result.objects,
            )
            total_findings += len(
                result.findings,
            )

            stopped = stopped or result.stopped

            self._collect_findings(
                result.findings,
                errors,
                warnings,
            )

            application_results.append(
                {
                    "application": application.name,
                    "path": str(application),
                    "files_scanned": result.files_scanned,
                    "objects": len(result.objects),
                    "findings": len(result.findings),
                    "stopped": result.stopped,
                    "report": str(report_path),
                },
            )

            changes.append(
                {
                    "application": application.name,
                    "action": "analyse",
                    "status": "completed",
                    "files_scanned": result.files_scanned,
                    "objects": len(result.objects),
                    "findings": len(result.findings),
                },
            )

        self.outputs.update(
            {
                "success": not errors,
                "files_scanned": total_files,
                "objects": total_objects,
                "findings": total_findings,
                "applications": len(
                    applications,
                ),
                "stopped": stopped,
                "results": application_results,
            },
        )

        return (
            changes,
            errors,
            warnings,
        )

    # ------------------------------------------------------------------
    # Application directories
    # ------------------------------------------------------------------

    @staticmethod
    def _application_directories(
        root: Path,
    ) -> list[Path]:
        """
        Return application directories below the analysis root.
        """

        return sorted(
            (
                path
                for path in root.iterdir()
                if path.is_dir()
                and path.name.casefold() != ".entropy"
            ),
            key=lambda path: path.name.casefold(),
        )

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _report_path(
        self,
        application: Path,
    ) -> Path:
        """
        Resolve the HTML report path for an application.
        """

        return (
            self.workspace
            / f"analyse_{application.name}.html"
        )

    # ------------------------------------------------------------------
    # Findings
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_findings(
        findings: tuple[AnalyseFinding, ...],
        errors: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> None:
        """
        Convert analysis findings into plugin result messages.
        """

        for finding in findings:

            item = {
                "rule": finding.rule,
                "severity": finding.severity,
                "file": str(finding.file),
                "line": finding.line,
                "column": finding.column,
                "message": finding.message,
            }

            severity = finding.severity.casefold()

            if severity in {
                "error",
                "stop",
            }:
                errors.append(
                    item,
                )

            elif severity == "warning":
                warnings.append(
                    item,
                )
