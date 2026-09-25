"""
Invalid objects report plugin.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .html import (
    HtmlReportObject,
    HtmlReportSchema,
    InvalidObjectsHtmlReport,
)
from .exceptions import InvalidObjectsReportPluginException
from .model import (
    InvalidObject,
    SchemaReport,
)
from .resolver import InvalidObjectsReportResolver

# Dependecy plugins
from ..generic.executor import SqlPlusExecutor
from ..generic.model import SqlPlusExecution

_INVALID_MARKER = "__ENTROPY_INVALID_OBJECTS__"
_ERRORS_MARKER = "__ENTROPY_USER_ERRORS__"


class InvalidObjectsReportPlugin(
    BasePlugin,
):
    """
    Generate an HTML report of invalid Oracle objects.
    """

    def execute(
        self,
    ) -> PluginResult:

        self.message.info(
            "Starting invalid_objects_report.",
        )

        with self.activity(
            "invalid_objects_report",
        ):

            reports = self._execute()

        self.message.success(
            "invalid_objects_report completed successfully.",
        )

        errors = [
            {
                "schema": report.schema,
                "type": report.error_type,
                "message": report.error_message,
            }
            for report in reports
            if report.status == "error"
        ]

        invalid_count = sum(
            len(report.invalid_objects)
            for report in reports
        )

        clean_count = sum(
            report.status == "clean"
            for report in reports
        )

        attention_count = sum(
            report.status == "attention"
            for report in reports
        )

        error_count = sum(
            report.status == "error"
            for report in reports
        )

        success = error_count == 0

        return PluginResult(
            success=success,
            changed=True,
            outputs=dict(
                self.outputs,
                schemas=len(reports),
                clean=clean_count,
                attention_required=attention_count,
                errors=error_count,
                invalid_objects=invalid_count,
            ),
            changes=[],
            errors=errors,
            warnings=[],
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
    ) -> list[SchemaReport]:

        connection = InvalidObjectsReportResolver.connection(
            self.arguments.dictionary(
                "connection",
            ),
        )

        schemas = InvalidObjectsReportResolver.schemas(
            self.arguments.dictionary(
                "schemas",
            ),
        )

        sqlhome = self.arguments.path(
            "sqlhome",
            None,
        )

        reports: list[SchemaReport] = []

        executor = SqlPlusExecutor(
            shell=self.shell,
            activity=self.activity,
            message=self.message,
        )

        for schema, credentials in schemas.items():

            self.message.info(
                f"Checking invalid objects for schema '{schema}'.",
            )

            report = self._inspect_schema(
                executor=executor,
                sqlhome=sqlhome,
                connection=connection,
                schema=schema,
                credentials=credentials,
            )

            reports.append(report)

        report_path = self._write_report(
            connection=connection,
            reports=reports,
        )

        self.artifacts["invalid_objects_report"] = report_path

        self.outputs.update(
            {
                "report": str(report_path),
                "connection": {
                    "host": connection["IP"],
                    "port": connection["PORT"],
                    "sid": connection["SID"],
                },
                "schemas": len(reports),
                "clean": sum(
                    report.status == "clean"
                    for report in reports
                ),
                "attention_required": sum(
                    report.status == "attention"
                    for report in reports
                ),
                "errors": sum(
                    report.status == "error"
                    for report in reports
                ),
                "invalid_objects": sum(
                    len(report.invalid_objects)
                    for report in reports
                ),
            },
        )

        return reports

    def _inspect_schema(
        self,
        *,
        executor: SqlPlusExecutor,
        sqlhome: Path | None,
        connection: dict[str, Any],
        schema: str,
        credentials: dict[str, Any],
    ) -> SchemaReport:

        script = self._create_script(
            schema,
        )

        execution = SqlPlusExecution(
            ip=connection["IP"],
            port=connection["PORT"],
            sid=connection["SID"],
            schema=schema,
            username=credentials["username"],
            password=credentials["password"],
            script=script,
        )

        result = executor.execute(
            sqlhome,
            execution,
        )

        #
        # The SQLPlus execution itself failed.
        #

        if not result.success:

            return SchemaReport(
                schema=schema,
                status="error",
                error_type=result.error_type,
                error_message=result.error_message,
                stderr=result.stderr,
            )

        try:

            invalid_objects, errors = self._parse_output(
                result.stdout,
            )

        except InvalidObjectsReportPluginException:

            raise

        except Exception as exc:

            raise InvalidObjectsReportPluginException(
                f"Unable to parse SQLPlus output for schema "
                f"'{schema}': {exc}",
            ) from exc

        error_map: dict[tuple[str, str], list[str]] = {}

        for name, object_type, text in errors:

            error_map.setdefault(
                (name, object_type),
                [],
            ).append(
                text,
            )

        objects = tuple(
            InvalidObject(
                name=name,
                object_type=object_type,
                status=status,
                errors=tuple(
                    error_map.get(
                        (name, object_type),
                        [],
                    ),
                ),
            )
            for name, object_type, status in invalid_objects
        )

        return SchemaReport(
            schema=schema,
            status=(
                "attention"
                if objects
                else "clean"
            ),
            invalid_objects=objects,
        )

    # ------------------------------------------------------------------
    # SQL generation
    # ------------------------------------------------------------------

    def _create_script(
        self,
        schema: str,
    ) -> Path:

        directory = self.workspace / ".entropy" / "invalid_objects"

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        safe_schema = "".join(
            character
            if character.isalnum() or character in {"_", "-"}
            else "_"
            for character in schema
        )

        path = directory / f"{safe_schema}.sql"

        script = f"""SET HEADING OFF
SET FEEDBACK OFF
SET PAGESIZE 0
SET LINESIZE 32767
SET VERIFY OFF
SET ECHO OFF
SET TERMOUT OFF
SET TRIMSPOOL ON
SET TAB OFF

PROMPT {_INVALID_MARKER}

SELECT
    object_name
    || '|'
    || object_type
    || '|'
    || status
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;

PROMPT {_ERRORS_MARKER}

SELECT
    name
    || '|'
    || type
    || '|'
    || REPLACE(
        REPLACE(
            text,
            CHR(10),
            ' '
        ),
        '|',
        '/'
    )
FROM user_errors
ORDER BY name, type, sequence;

EXIT
"""

        path.write_text(
            script,
            encoding="utf-8",
        )

        return path

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_output(
        self,
        stdout: str,
    ) -> tuple[
        list[tuple[str, str, str]],
        list[tuple[str, str, str]],
    ]:

        section: str | None = None

        invalid_objects: list[
            tuple[str, str, str]
        ] = []

        errors: list[
            tuple[str, str, str]
        ] = []

        for raw_line in stdout.splitlines():

            line = raw_line.strip()

            if not line:
                continue

            if line == _INVALID_MARKER:
                section = "invalid"
                continue

            if line == _ERRORS_MARKER:
                section = "errors"
                continue

            if section == "invalid":

                parts = line.split(
                    "|",
                    2,
                )

                if len(parts) != 3:
                    continue

                name, object_type, status = (
                    part.strip()
                    for part in parts
                )

                if name:
                    invalid_objects.append(
                        (
                            name,
                            object_type,
                            status,
                        ),
                    )

            elif section == "errors":

                parts = line.split(
                    "|",
                    2,
                )

                if len(parts) != 3:
                    continue

                name, object_type, text = (
                    part.strip()
                    for part in parts
                )

                if name and text:
                    errors.append(
                        (
                            name,
                            object_type,
                            text,
                        ),
                    )

        return invalid_objects, errors

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def _write_report(
        self,
        *,
        connection: dict[str, Any],
        reports: list[SchemaReport],
    ) -> Path:

        generated_at = datetime.now(
            timezone.utc,
        )

        timestamp = generated_at.strftime(
            "%Y%m%d_%H%M%S",
        )

        report_name = (
            f"invalid_objects_{timestamp}.html"
        )

        report_path = (
            self.workspace / report_name
        )

        generated_by = self._username()

        html_schemas = tuple(
            HtmlReportSchema(
                name=report.schema,
                status=report.status,
                invalid_objects=tuple(
                    HtmlReportObject(
                        name=obj.name,
                        object_type=obj.object_type,
                        status=obj.status,
                        errors=obj.errors,
                    )
                    for obj in report.invalid_objects
                ),
                error_type=report.error_type,
                error_message=report.error_message,
                stderr=report.stderr,
            )
            for report in reports
        )

        html = InvalidObjectsHtmlReport().render(
            report_name=report_name,
            generated_at=generated_at,
            generated_by=generated_by,
            host=connection["IP"],
            port=connection["PORT"],
            sid=connection["SID"],
            schemas=html_schemas,
        )

        report_path.write_text(
            html,
            encoding="utf-8",
        )

        return report_path

    def _username(
        self,
    ) -> str:

        username = getattr(
            self.user,
            "username",
            None,
        )

        if isinstance(username, str) and username.strip():
            return username.strip()

        return "unknown"
