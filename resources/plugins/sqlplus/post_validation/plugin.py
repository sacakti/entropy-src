"""
Post-deployment SQLPlus validation plugin.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import PostValidationPluginException
from .validator import PostValidationValidator


class PostValidationPlugin(BasePlugin):
    """
    Validate or analyze SQLPlus deployment logs per application.
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
        Discover applications and generate post-validation reports.
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

        archive = self.arguments.boolean(
            "archive",
            False,
        )

        embed_log = self.arguments.boolean(
            "embed_log",
            True,
        )

        applications = self._application_directories(
            base,
        )

        if not applications:
            raise PostValidationPluginException(
                f"No application directories found under: {base}",
            )

        self.workspace.mkdir(
            parents=True,
            exist_ok=True,
        )

        if archive:
            archive_root = (
                self.workspace
                / "post_validation_archive"
            )

            archive_root.mkdir(
                parents=True,
                exist_ok=True,
            )
        else:
            archive_root = None

        validator = PostValidationValidator()

        changes: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        application_reports: list[dict[str, Any]] = []

        for application in applications:
            result = self._process_application(
                application=application,
                validator=validator,
                embed_log=embed_log,
                archive_root=archive_root,
            )

            application_reports.append(
                result["dashboard"],
            )

            changes.append(
                result["change"],
            )

            errors.extend(
                result["errors"],
            )

            warnings.extend(
                result["warnings"],
            )

        dashboard = self._build_dashboard(
            base=base,
            reports=application_reports,
        )

        self.artifacts[
            "post_validation_dashboard"
        ] = dashboard

        self.outputs.update(
            {
                "success": not errors,
                "dashboard": str(dashboard),
                "applications": len(applications),
                "validated": sum(
                    1
                    for item in application_reports
                    if item["mode"] == "validation"
                ),
                "analyzed": sum(
                    1
                    for item in application_reports
                    if item["mode"] == "log-only"
                ),
                "failed": sum(
                    1
                    for item in application_reports
                    if item["status"] == "fail"
                ),
                "warnings": len(warnings),
                "results": application_reports,
            },
        )

        return (
            changes,
            errors,
            warnings,
        )

    # ------------------------------------------------------------------
    # Application processing
    # ------------------------------------------------------------------

    def _process_application(
        self,
        *,
        application: Path,
        validator: PostValidationValidator,
        embed_log: bool,
        archive_root: Path | None,
    ) -> dict[str, Any]:
        """
        Validate or analyze one application.
        """

        application_name = application.name

        json_path = self._find_pre_validation(
            application,
        )

        log_path = self._resolve_log(
            application,
        )

        if archive_root is not None:
            self._archive_application(
                application=application,
                json_path=json_path,
                log_path=log_path,
                archive_root=archive_root,
            )

        output = (
            self.workspace
            / (
                f"{self._safe_name(application_name)}"
                "_post_validation.html"
            )
        )

        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        if json_path is not None:
            self.message.info(
                f"{application_name}: "
                f"pre-validation found: {json_path}",
            )

            validation = validator.validate(
                json_path=json_path,
                log_path=log_path,
            )

            report = validator.build_dashboard(
                result=validation,
                output=output,
                embed_log=embed_log,
            )

            self.artifacts[
                f"post_validation_{self._safe_name(application_name)}"
            ] = report

            for associate in validation.associates:
                item = {
                    "application": application_name,
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

            status = (
                "fail"
                if errors
                else "pass"
            )

            return {
                "dashboard": {
                    "application": application_name,
                    "mode": "validation",
                    "status": status,
                    "report": str(report),
                    "log": str(log_path),
                    "pre_validation": str(json_path),
                    "release": validation.release,
                    "errors": validation.error_lines,
                    "mismatches": validation.count_mismatches,
                    "passed": validation.passed,
                    "failed": validation.failed,
                    "partial": validation.partial,
                    "notrun": validation.notrun,
                },
                "change": {
                    "action": "post_validation",
                    "status": "completed",
                    "application": application_name,
                    "mode": "validation",
                    "dashboard": str(report),
                },
                "errors": errors,
                "warnings": warnings,
            }

        self.message.info(
            f"{application_name}: "
            "pre-validation JSON not found; "
            "running log-only analysis.",
        )

        analysis = validator.analyze(
            log_path=log_path,
        )

        report = validator.build_log_analysis(
            log_path=log_path,
            analysis=analysis,
            output=output,
            release=application_name,
            embed_log=embed_log,
        )

        self.artifacts[
            f"post_validation_{self._safe_name(application_name)}"
        ] = report

        log_errors = analysis.get(
            "errors",
            [],
        )

        log_notes = analysis.get(
            "notes",
            [],
        )

        for error in log_errors:
            errors.append(
                {
                    "application": application_name,
                    "mode": "log-only",
                    "file": getattr(
                        error,
                        "file",
                        "—",
                    ),
                    "line": getattr(
                        error,
                        "line",
                        0,
                    ),
                    "message": getattr(
                        error,
                        "message",
                        str(error),
                    ),
                },
            )

        for note in log_notes:
            warnings.append(
                {
                    "application": application_name,
                    "mode": "log-only",
                    "file": getattr(
                        note,
                        "file",
                        "—",
                    ),
                    "line": getattr(
                        note,
                        "line",
                        0,
                    ),
                    "message": getattr(
                        note,
                        "message",
                        str(note),
                    ),
                },
            )

        status = (
            "fail"
            if log_errors
            else "analyzed"
        )

        return {
            "dashboard": {
                "application": application_name,
                "mode": "log-only",
                "status": status,
                "report": str(report),
                "log": str(log_path),
                "pre_validation": None,
                "release": application_name,
                "errors": len(log_errors),
                "notes": len(log_notes),
                "files_analyzed": len(
                    analysis.get(
                        "per_file",
                        {},
                    ),
                ),
            },
            "change": {
                "action": "post_validation",
                "status": "completed",
                "application": application_name,
                "mode": "log-only",
                "dashboard": str(report),
            },
            "errors": errors,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _application_directories(
        base: Path,
    ) -> list[Path]:
        """
        Return immediate application directories.

        The execution workspace metadata directory is ignored.
        """

        return sorted(
            (
                path
                for path in base.iterdir()
                if path.is_dir()
                and path.name.casefold() != ".entropy"
            ),
            key=lambda path: path.name.casefold(),
        )

    @staticmethod
    def _find_pre_validation(
        application: Path,
    ) -> Path | None:
        """
        Find the application's pre-validation JSON.

        The file is optional. If it does not exist, log-only
        analysis is performed.
        """

        direct = (
            application
            / "pre_validation.json"
        )

        if direct.is_file():
            return direct.resolve()

        matches = sorted(
            (
                path
                for path in application.rglob(
                    "pre_validation.json",
                )
                if path.is_file()
            ),
            key=lambda path: str(path).casefold(),
        )

        if not matches:
            return None

        return matches[0].resolve()

    @staticmethod
    def _resolve_log(
        application: Path,
    ) -> Path:
        """
        Resolve the application's deployment log.

        Prefer logs below the application's logs directory.
        If that directory does not exist, search the application
        recursively and use the newest log.
        """

        logs_directory = (
            application
            / "logs"
        )

        if logs_directory.is_dir():
            logs = [
                path
                for path in logs_directory.rglob("*")
                if path.is_file()
                and path.suffix.casefold() == ".log"
            ]
        else:
            logs = [
                path
                for path in application.rglob("*")
                if path.is_file()
                and path.suffix.casefold() == ".log"
            ]

        if not logs:
            raise PostValidationPluginException(
                "No deployment log found for "
                f"application '{application.name}' "
                f"under: {application}",
            )

        return max(
            logs,
            key=lambda path: path.stat().st_mtime,
        ).resolve()

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------

    @staticmethod
    def _archive_application(
        *,
        application: Path,
        json_path: Path | None,
        log_path: Path,
        archive_root: Path,
    ) -> None:
        """
        Copy source validation files into the workspace archive.

        Source files are never modified or moved.
        """

        destination = (
            archive_root
            / application.name
        )

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        if json_path is not None:
            shutil.copy2(
                json_path,
                destination / "pre_validation.json",
            )

        shutil.copy2(
            log_path,
            destination / log_path.name,
        )

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def _build_dashboard(
        self,
        *,
        base: Path,
        reports: list[dict[str, Any]],
    ) -> Path:
        """
        Build the top-level application dashboard.
        """

        output = (
            self.workspace
            / "post_validation.html"
        )

        rows: list[str] = []

        for item in reports:
            application = self._escape(
                item["application"],
            )

            report_path = Path(
                item["report"],
            )

            report_name = self._escape(
                report_path.name,
            )

            mode = self._escape(
                item["mode"],
            )

            status = self._escape(
                item["status"],
            )

            rows.append(
                f"""
<tr>
    <td>
        <strong>{application}</strong>
    </td>
    <td>{mode}</td>
    <td>
        <span class="status {status.lower()}">
            {status}
        </span>
    </td>
    <td>
        <a href="{report_name}">
            Open report
        </a>
    </td>
</tr>
"""
            )

        validation_count = sum(
            1
            for item in reports
            if item["mode"] == "validation"
        )

        analyzed_count = sum(
            1
            for item in reports
            if item["mode"] == "log-only"
        )

        failed_count = sum(
            1
            for item in reports
            if item["status"] == "fail"
        )

        document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>Post Validation</title>

<style>
    * {{
        box-sizing: border-box;
    }}

    body {{
        margin: 0;
        padding: 0;
        background: #f4f6f8;
        color: #202124;
        font-family:
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            Roboto,
            Arial,
            sans-serif;
    }}

    .container {{
        width: min(1200px, 96%);
        margin: 0 auto;
        padding: 28px 0 48px;
    }}

    h1 {{
        margin: 0;
    }}

    .subtitle {{
        margin-top: 8px;
        color: #667085;
        font-size: 14px;
    }}

    .cards {{
        display: grid;
        grid-template-columns:
            repeat(auto-fit, minmax(170px, 1fr));
        gap: 12px;
        margin: 24px 0;
    }}

    .card {{
        background: white;
        border: 1px solid #e4e7ec;
        border-radius: 10px;
        padding: 18px;
    }}

    .label {{
        color: #667085;
        font-size: 12px;
        text-transform: uppercase;
    }}

    .value {{
        margin-top: 6px;
        font-size: 26px;
        font-weight: 700;
    }}

    .panel {{
        background: white;
        border: 1px solid #e4e7ec;
        border-radius: 10px;
        overflow: hidden;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
    }}

    th,
    td {{
        padding: 12px;
        border-bottom: 1px solid #eaecf0;
        text-align: left;
    }}

    th {{
        background: #f8fafc;
    }}

    tr:last-child td {{
        border-bottom: 0;
    }}

    .status {{
        display: inline-block;
        border-radius: 999px;
        padding: 5px 10px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
    }}

    .status.pass {{
        background: #dcfce7;
        color: #166534;
    }}

    .status.fail {{
        background: #fee2e2;
        color: #991b1b;
    }}

    .status.analyzed {{
        background: #e0f2fe;
        color: #075985;
    }}

    .status.log-only {{
        background: #e0f2fe;
        color: #075985;
    }}

    a {{
        color: #175cd3;
        text-decoration: none;
    }}

    a:hover {{
        text-decoration: underline;
    }}
</style>
</head>

<body>
<div class="container">

    <h1>Post Validation</h1>

    <div class="subtitle">
        Source:
        {self._escape(str(base))}
    </div>

    <div class="cards">

        <div class="card">
            <div class="label">
                Applications
            </div>
            <div class="value">
                {len(reports)}
            </div>
        </div>

        <div class="card">
            <div class="label">
                Validation Mode
            </div>
            <div class="value">
                {validation_count}
            </div>
        </div>

        <div class="card">
            <div class="label">
                Log-only Mode
            </div>
            <div class="value">
                {analyzed_count}
            </div>
        </div>

        <div class="card">
            <div class="label">
                Failed
            </div>
            <div class="value">
                {failed_count}
            </div>
        </div>

    </div>

    <div class="panel">

        <table>
            <thead>
                <tr>
                    <th>Application</th>
                    <th>Mode</th>
                    <th>Status</th>
                    <th>Report</th>
                </tr>
            </thead>

            <tbody>
                {"".join(rows)}
            </tbody>
        </table>

    </div>

</div>
</body>
</html>
"""

        output.write_text(
            document,
            encoding="utf-8",
        )

        return output

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

        return (
            value.strip(
                "_",
            )
            or "application"
        )

    @staticmethod
    def _escape(
        value: object,
    ) -> str:
        """
        Escape a value for HTML.
        """

        import html

        return html.escape(
            str(value),
            quote=True,
        )
