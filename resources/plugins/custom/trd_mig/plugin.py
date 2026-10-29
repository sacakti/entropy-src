"""
TRD migration plugin.

Truncates the configured tables (optional), checks that the product's
table is empty, runs the country's SQL file and reports the resulting
row count.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Dependency plugin (declared in plugin.json required_plugins).
from sqlplus.generic.executor import SqlPlusExecutor
from sqlplus.generic.model import SqlPlusExecution

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import TrdMigPluginException
from .resolver import TrdMigResolver

_COUNT_MARKER = "__ENTROPY_COUNT__"

_MAPPING_FILENAME = "mapping.json"

_DEFAULT_TRUNCATE_PROFILE = "default"

# Country SQL files live in this folder next to the mapping file.
_SQLS_DIRECTORY = "sqls"

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


class TrdMigPlugin(BasePlugin):
    """
    Migrate TRD data for one product and country.
    """

    _inserted = False

    def execute(
        self,
    ) -> PluginResult:
        """
        Run the TRD migration.
        """

        self.message.info(
            "Starting trd_mig.",
        )

        try:
            with self.activity("trd_mig"):
                self._execute()

        except TrdMigPluginException as exc:
            self.log.error(str(exc))
            self.message.error(str(exc))

            return self._result(
                success=False,
                errors=[str(exc)],
            )

        self.message.success(
            "trd_mig completed successfully.",
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

        connection = TrdMigResolver.connection(
            self.arguments.dictionary(
                "connection",
                required=True,
            ),
        )

        credentials = TrdMigResolver.credentials(
            self.arguments.get(
                "credentials",
            ),
        )

        country = (
            self.arguments.string(
                "country",
                required=True,
            )
            or ""
        )

        product = (
            self.arguments.string(
                "product",
                required=True,
            )
            or ""
        )

        truncate = self.arguments.boolean(
            "truncate",
            False,
        )

        truncate_profile = self.arguments.string(
            "truncate_profile",
            _DEFAULT_TRUNCATE_PROFILE,
        )

        truncate_tables = self.arguments.list(
            "truncate_tables",
            None,
        )

        sqlhome = self.arguments.path(
            "sqlhome",
            None,
        )

        mapping_path = self.arguments.path(
            "mapping",
            None,
        ) or (Path(__file__).resolve().parent / _MAPPING_FILENAME)

        settings = TrdMigResolver.mapping(
            self._read_mapping(mapping_path),
            country=country,
            product=product,
            # Profiles are only resolved when the truncate step runs.
            truncate_profile=truncate_profile if truncate else None,
            truncate_tables=truncate_tables if truncate else None,
        )

        sql_path = mapping_path.parent / _SQLS_DIRECTORY / settings["sql_file"]

        # Read before anything runs, so a missing file changes nothing.
        insert_sql = TrdMigResolver.sql(
            self._read_sql(sql_path),
            country=country,
            product=product,
            dblink=settings["dblink"],
            sql_file=settings["sql_file"],
        )

        self.outputs.update(
            {
                "country": country,
                "product": product,
                "count_table": settings["count_table"],
                "sql_file": settings["sql_file"],
                "truncated": [],
            },
        )

        executor = SqlPlusExecutor(
            shell=self.shell,
            activity=self.activity,
            message=self.message,
        )

        execution = _Runner(
            plugin=self,
            executor=executor,
            sqlhome=sqlhome,
            connection=connection,
            credentials=credentials,
            product=product,
        )

        # 1. Truncate.

        if truncate and settings["truncate"]:

            execution.run(
                "truncate",
                "".join(f"TRUNCATE TABLE {table};\n" for table in settings["truncate"]),
            )

            self.outputs["truncated"] = list(settings["truncate"])

            self.message.success(
                f"Truncated {', '.join(settings['truncate'])} " f"({settings['truncate_source']}).",
            )

        elif truncate:
            self.message.warning(
                f"No tables to truncate ({settings['truncate_source']}).",
            )

        else:
            self.message.info(
                "Truncate skipped.",
            )

        # 2. Count before insert must be zero.

        count_before = execution.count(
            settings["count_table"],
        )

        self.outputs["count_before"] = count_before

        self.message.info(
            f"{settings['count_table']} has {count_before} row(s) before the insert.",
        )

        if count_before > 0 and not self._consent(
            settings["count_table"],
            count_before,
        ):
            raise TrdMigPluginException(
                f"Stopped: {settings['count_table']} is not empty "
                f"({count_before} row(s)) and the insert was not confirmed.",
            )

        # 3. Insert.

        self.message.info(
            f"Running {settings['sql_file']} for {country}.",
        )

        execution.run(
            "insert",
            f"{insert_sql}\nCOMMIT;\n",
        )

        self._inserted = True

        self.message.success(
            f"Ran {settings['sql_file']} for {product} ({country}).",
        )

        # 4. Count after insert.

        count_after = execution.count(
            settings["count_table"],
        )

        self.outputs.update(
            {
                "count_after": count_after,
                "counts": {
                    product: count_after,
                },
            },
        )

        self.message.success(
            f"{product}: {settings['count_table']} has {count_after} row(s).",
        )

    def _read_mapping(
        self,
        path: Path,
    ) -> Any:

        if not self.filesystem.is_file(path):
            raise TrdMigPluginException(
                f"Mapping file does not exist: {path}",
            )

        try:
            return self.filesystem.read_json(path)

        except (OSError, ValueError) as exc:
            raise TrdMigPluginException(
                f"Unable to read mapping file '{path}': {exc}",
            ) from exc

    def _read_sql(
        self,
        path: Path,
    ) -> str:

        if not self.filesystem.is_file(path):
            raise TrdMigPluginException(
                f"SQL file does not exist: {path}",
            )

        try:
            return str(self.filesystem.read_text(path))

        except (OSError, ValueError) as exc:
            raise TrdMigPluginException(
                f"Unable to read SQL file '{path}': {exc}",
            ) from exc

    def _consent(
        self,
        table: str,
        count: int,
    ) -> bool:

        answer = self.ask(
            f"{table} already has {count} row(s). Proceed with the insert?",
            name="trd_mig_proceed",
            default="no",
            description="The table is expected to be empty before the insert.",
            choices=["yes", "no"],
        )

        return answer.strip().casefold() in {"y", "yes"}

    def _result(
        self,
        *,
        success: bool,
        errors: list[str] | None = None,
    ) -> PluginResult:

        return PluginResult(
            success=success,
            changed=self._inserted or bool(self.outputs.get("truncated")),
            outputs=dict(self.outputs),
            changes=[],
            errors=errors or [],
            warnings=[],
            metadata={},
        )


class _Runner:
    """
    Run generated SQLPlus scripts against one schema.
    """

    def __init__(
        self,
        *,
        plugin: TrdMigPlugin,
        executor: SqlPlusExecutor,
        sqlhome: Path | None,
        connection: dict[str, Any],
        credentials: dict[str, str],
        product: str,
    ) -> None:

        self._plugin = plugin
        self._executor = executor
        self._sqlhome = sqlhome
        self._connection = connection
        self._credentials = credentials
        self._product = product

    def run(
        self,
        name: str,
        body: str,
    ) -> str:
        """
        Run one script and return its stdout.
        """

        directory = self._plugin.workspace / "trd_mig_scripts"

        self._plugin.filesystem.mkdir(
            directory,
        )

        script = directory / f"{self._product}_{name}.sql"

        self._plugin.filesystem.write_text(
            script,
            f"{_SCRIPT_SETTINGS}\n{body}\nEXIT\n",
        )

        execution = SqlPlusExecution(
            ip=self._connection["IP"],
            port=self._connection["PORT"],
            sid=self._connection["SID"],
            schema=self._credentials["username"],
            username=self._credentials["username"],
            password=self._credentials["password"],
            script=script,
            application="trd_mig",
        )

        result = self._executor.execute(
            self._sqlhome,
            execution,
        )

        if not result.success:
            raise TrdMigPluginException(
                f"SQLPlus {name} step failed: "
                f"{result.error_message or result.stderr or 'unknown error'}",
            )

        return str(result.stdout)

    def count(
        self,
        table: str,
    ) -> int:
        """
        Return the row count of a table.
        """

        stdout = self.run(
            "count",
            f"SELECT '{_COUNT_MARKER}|' || COUNT(*) FROM {table};\n",
        )

        return parse_count(stdout)


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

    raise TrdMigPluginException(
        "Unable to read the row count from SQLPlus output.",
    )
