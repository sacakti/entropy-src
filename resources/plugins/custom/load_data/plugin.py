"""
Load data plugin.

Runs the configured procedure SQL files (from the sqls folder) in order.
After each one, counts the rows of its status table that are not
successful and stops when there are any.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Dependency plugin (declared in plugin.json required_plugins).
from sqlplus.generic.executor import SqlPlusExecutor
from sqlplus.generic.model import SqlPlusExecution

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import LoadDataPluginException
from .resolver import LoadDataResolver

_COUNT_MARKER = "__ENTROPY_COUNT__"

_DEFAULT_PROCEDURES = ["procedure1.sql", "procedure2.sql"]

# Procedure SQL files live in this folder of the plugin.
_SQLS_DIRECTORY = Path(__file__).resolve().parent / "sqls"

_SCRIPT_SETTINGS = """WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
SET HEADING OFF
SET FEEDBACK ON
SET PAGESIZE 0
SET LINESIZE 32767
SET VERIFY OFF
SET ECHO OFF
SET DEFINE OFF
SET TRIMSPOOL ON
"""


class LoadDataPlugin(BasePlugin):
    """
    Run load procedures in order, checking their status after each.
    """

    _procedure_ran = False

    def execute(
        self,
    ) -> PluginResult:
        """
        Run the load procedures.
        """

        self.message.info(
            "Starting load_data.",
        )

        try:
            with self.activity("load_data"):
                self._execute()

        except LoadDataPluginException as exc:
            self.log.error(str(exc))
            self.message.error(str(exc))

            return self._result(
                success=False,
                errors=[str(exc)],
            )

        self.message.success(
            "load_data completed successfully.",
        )

        return self._result(
            success=True,
        )

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> None:

        connection = LoadDataResolver.connection(
            self.arguments.dictionary(
                "connection",
                required=True,
            ),
        )

        credentials = LoadDataResolver.credentials(
            self.arguments.get(
                "credentials",
            ),
        )

        procedures = LoadDataResolver.procedures(
            self.arguments.list(
                "procedures",
                _DEFAULT_PROCEDURES,
            ),
            self.arguments.dictionary(
                "status_check",
                None,
            ),
        )

        sqlhome = self.arguments.path(
            "sqlhome",
            None,
        )

        # Read every file before anything runs, so a missing one changes nothing.
        scripts = [self._read_sql(step["sql"]) for step in procedures]

        executor = SqlPlusExecutor(
            shell=self.shell,
            activity=self.activity,
            message=self.message,
        )

        results: list[dict[str, Any]] = []

        self.outputs.update(
            {
                "procedures": len(procedures),
                "completed": 0,
                "results": results,
            },
        )

        for index, step in enumerate(procedures, start=1):

            procedure = step["sql"]
            check = step["status_check"]

            self.message.info(
                f"Running {procedure} and waiting for it to complete.",
            )

            self._run(
                executor=executor,
                sqlhome=sqlhome,
                connection=connection,
                credentials=credentials,
                name=f"{index}_procedure",
                body=f"{scripts[index - 1]}\n",
            )

            self._procedure_ran = True

            self.message.success(
                f"{procedure} completed.",
            )

            stdout = self._run(
                executor=executor,
                sqlhome=sqlhome,
                connection=connection,
                credentials=credentials,
                name=f"{index}_status",
                body=(
                    f"SELECT '{_COUNT_MARKER}|' || COUNT(*) FROM {check['table']}\n"
                    f"WHERE {check['column']} IS NULL\n"
                    f"   OR {check['column']} <> '{check['success_value']}';\n"
                ),
            )

            pending = parse_count(stdout)

            results.append(
                {
                    "sql": procedure,
                    "table": check["table"],
                    "not_successful": pending,
                },
            )

            if pending > 0:
                raise LoadDataPluginException(
                    f"Stopped after {procedure}: {pending} row(s) in {check['table']} "
                    f"have {check['column']} other than "
                    f"'{check['success_value']}'. Check them before running again.",
                )

            self.outputs["completed"] = index

            self.message.success(
                f"{check['table']}: all rows are successful after {procedure}.",
            )

    def _read_sql(
        self,
        name: str,
    ) -> str:

        path = _SQLS_DIRECTORY / name

        if not self.filesystem.is_file(path):
            raise LoadDataPluginException(
                f"SQL file does not exist: {path}",
            )

        try:
            text = str(self.filesystem.read_text(path)).rstrip()

        except (OSError, ValueError) as exc:
            raise LoadDataPluginException(
                f"Unable to read SQL file '{path}': {exc}",
            ) from exc

        if not text:
            raise LoadDataPluginException(
                f"SQL file '{name}' is empty.",
            )

        return text

    def _run(
        self,
        *,
        executor: SqlPlusExecutor,
        sqlhome: Path | None,
        connection: dict[str, Any],
        credentials: dict[str, str],
        name: str,
        body: str,
    ) -> str:
        """
        Run one generated script and return its stdout.

        SQLPlus returns only when the script has finished, so a
        procedure call waits for the procedure to complete.
        """

        directory = self.workspace / "load_data_scripts"

        self.filesystem.mkdir(
            directory,
        )

        script = directory / f"{name}.sql"

        self.filesystem.write_text(
            script,
            f"{_SCRIPT_SETTINGS}\n{body}\nEXIT\n",
        )

        execution = SqlPlusExecution(
            ip=connection["IP"],
            port=connection["PORT"],
            sid=connection["SID"],
            schema=credentials["username"],
            username=credentials["username"],
            password=credentials["password"],
            script=script,
            application="load_data",
        )

        result = executor.execute(
            sqlhome,
            execution,
        )

        if not result.success:
            raise LoadDataPluginException(
                f"SQLPlus script '{name}' failed: "
                f"{result.error_message or result.stderr or 'unknown error'}",
            )

        return str(result.stdout)

    def _result(
        self,
        *,
        success: bool,
        errors: list[str] | None = None,
    ) -> PluginResult:

        return PluginResult(
            success=success,
            changed=self._procedure_ran,
            outputs=dict(self.outputs),
            changes=[],
            errors=errors or [],
            warnings=[],
            metadata={},
        )


def parse_count(
    stdout: str,
) -> int:
    """
    Read the marked COUNT(*) value from SQLPlus output.
    """

    for line in stdout.splitlines():

        line = line.strip()

        if line.startswith(f"{_COUNT_MARKER}|"):

            value = line.split("|", 1)[1].strip()

            if value.isdigit():
                return int(value)

    raise LoadDataPluginException(
        "Unable to read the row count from SQLPlus output.",
    )
