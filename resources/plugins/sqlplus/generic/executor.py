"""
SQLPlus command execution.
"""

from __future__ import annotations
from typing import Any

from pathlib import Path
import re
import subprocess
import time
from typing import TYPE_CHECKING

from .exceptions import GenericPluginError

from .model import (
    SqlPlusExecution,
    SqlPlusExecutionResult,
    SpoolSettings
)
from .spool.resolver import SpoolSettingsResolver
from .spool.wrapper import SpoolScriptBuilder

if TYPE_CHECKING:
    from lib.executor.result import ExecutionResult

_ORACLE_ERROR = re.compile(
    r"^\s*(?:ORA|SP2|PLS)-\d+",
    re.IGNORECASE | re.MULTILINE,
)

class SqlPlusExecutor:
    """
    Execute SQLPlus scripts through Entropy's shell abstraction.
    """


    def __init__(
        self,
        *,
        shell,
        activity,
    ) -> None:
        self._shell = shell
        self._activity = activity
        self._spool_builder = SpoolScriptBuilder()

    @staticmethod
    def build_command(
        execution: SqlPlusExecution,
        *,
        script: Path | None = None,
    ) -> tuple[list[str], list[str]]:
        """
        Build the actual and display-safe SQLPlus commands.
        """

        connection = (
            f"{execution.username}/"
            f"{execution.password}@//"
            f"{execution.ip}:"
            f"{execution.port}/"
            f"{execution.sid}"
        )

        safe_connection = (
            f"{execution.username}/"
            "****@//"
            f"{execution.ip}:"
            f"{execution.port}/"
            f"{execution.sid}"
        )

        script_path = script or execution.script

        command = [
            "sqlplus",
            connection,
            f"@{script_path}",
        ]

        display_command = [
            "sqlplus",
            safe_connection,
            f"@{script_path}",
        ]

        return command, display_command

    def execute(
        self,
        execution: SqlPlusExecution,
        *,
        timeout: int | None = None,
        spool_settings: SpoolSettings | None = None,
        execution_path: Path | None = None,
        release: str = "release",
    ) -> SqlPlusExecutionResult:
        """
        Execute one SQLPlus script.
        """
        settings = spool_settings or SpoolSettings()

        spool_path: Path | None = None
        spool_metadata: dict[str, Any]

        script = execution.script

        # --------------------------------------------------------------
        # Always detect an existing spool.
        # --------------------------------------------------------------

        existing_spool = (
            self._spool_builder.detect_spool(
                execution.script,
            )
        )

        existing_spool_valid = (
            existing_spool is not None
            and self._spool_builder.is_valid_spool(
                existing_spool,
            )
        )

        # --------------------------------------------------------------
        # No Entropy spool management.
        #
        # Execute the original script exactly as supplied.
        # If it contains SPOOL, report that spool.
        # --------------------------------------------------------------

        if not settings.enabled:

            spool_path = existing_spool

            spool_metadata = self._build_spool_metadata(
                settings=settings,
                existing_spool=existing_spool,
                existing_spool_valid=existing_spool_valid,
                used_spool=spool_path,
            )

        # --------------------------------------------------------------
        # Entropy spool management enabled.
        # --------------------------------------------------------------

        else:

            if execution_path is None:
                raise GenericPluginError(
                    "execution_path is required when spool is enabled.",
                )

            configured_spool_path = (
                SpoolSettingsResolver.resolve_path(
                    settings.name_placeholder,
                    execution_path=execution_path,
                    release=release,
                    schema=execution.schema,
                )
            )

            if settings.create_if_not_exists:
                configured_spool_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

            if existing_spool_valid and not settings.override:

                spool_path = existing_spool

            else:

                spool_path = configured_spool_path

                wrapper_directory = (
                    execution_path
                    / ".entropy"
                    / "sqlplus"
                )

                wrapper_directory.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                wrapper = (
                    wrapper_directory
                    / (
                        f"{execution.script.stem}_"
                        f"{execution.schema}_spool.sql"
                    )
                )

                script = self._spool_builder.build(
                    script=execution.script,
                    spool_path=spool_path,
                    settings=settings,
                    destination=wrapper,
                )

            spool_metadata = self._build_spool_metadata(
                settings=settings,
                existing_spool=existing_spool,
                existing_spool_valid=existing_spool_valid,
                used_spool=spool_path,
            )

        command, display_command = self.build_command(
            execution,
            script=script,
        )

        start = time.perf_counter()

        try:
            result = self._shell.run(
                command=command,
                display_command=display_command,
                cwd=execution.script.parent,
                timeout=timeout,
            )

        except FileNotFoundError as exc:
            duration = time.perf_counter() - start

            return SqlPlusExecutionResult(
                schema=execution.schema,
                script=execution.script,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=(
                    "SQLPlus executable was not found. "
                    "Ensure 'sqlplus' is installed and available "
                    "on PATH."
                ),
                duration=duration,
                spool=spool_metadata,
            )

        except TimeoutError as exc:
            duration = time.perf_counter() - start

            return SqlPlusExecutionResult(
                schema=execution.schema,
                script=execution.script,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=(
                    f"SQLPlus execution timed out: {exc}"
                ),
                duration=duration,
                spool=spool_metadata,
            )


        except subprocess.TimeoutExpired as exc:
            duration = time.perf_counter() - start

            return SqlPlusExecutionResult(
                schema=execution.schema,
                script=execution.script,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=(
                    f"SQLPlus execution timed out: {exc}"
                ),
                duration=duration,
                spool=spool_metadata,
            )

        except OSError as exc:
            duration = time.perf_counter() - start

            return SqlPlusExecutionResult(
                schema=execution.schema,
                script=execution.script,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=(
                    f"Unable to execute SQLPlus: {exc}"
                ),
                duration=duration,
                spool=spool_metadata,
            )

        return self.interpret_result(
            execution,
            result,
            spool_metadata=spool_metadata,
        )

    def execute_all(
        self,
        executions: list[SqlPlusExecution],
        *,
        on_error: str,
        timeout: int | None = None,
        spool_settings: SpoolSettings | None = None,
        execution_path: Path | None = None,
        release: str = "release",
    ) -> list[SqlPlusExecutionResult]:
        """
        Execute multiple SQLPlus scripts according to the error policy.
        """

        results: list[SqlPlusExecutionResult] = []

        for execution in executions:

            activity_name = (
                f"{execution.schema}/{execution.script.name}"
            )

            with self._activity(
                activity_name,
            ):
                result = self.execute(
                    execution,
                    timeout=timeout,
                    spool_settings=spool_settings,
                    execution_path=execution_path,
                    release=release,
                )

            results.append(result)

            if (
                not result.success
                and on_error == "abort"
            ):
                break

        return results

    @staticmethod
    def _contains_sqlplus_error(
        stdout: str,
        stderr: str,
    ) -> bool:
        output = f"{stdout}\n{stderr}"

        return bool(
            _ORACLE_ERROR.search(output),
        )

    @staticmethod
    def interpret_result(
        execution: SqlPlusExecution,
        result: ExecutionResult,
        *,
        spool_metadata: Path | None = None,
    ) -> SqlPlusExecutionResult:

        sqlplus_error = (
            result.exit_code != 0
            or SqlPlusExecutor._contains_sqlplus_error(
                result.stdout,
                result.stderr,
            )
        )

        return SqlPlusExecutionResult(
            schema=execution.schema,
            script=execution.script,
            success=not sqlplus_error,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration=result.duration,
            spool=spool_metadata,
        )

    # Helper
    def _build_spool_metadata(
        self,
        *,
        settings: SpoolSettings,
        existing_spool: Path | None,
        existing_spool_valid: bool,
        used_spool: Path | None,
    ) -> dict[str, Any]:
        """
        Build spool execution metadata.
        """

        return {
            "enabled": settings.enabled,
            "detected": existing_spool is not None,
            "existing": (
                str(existing_spool)
                if existing_spool is not None
                else None
            ),
            "used": (
                str(used_spool)
                if used_spool is not None
                else None
            ),
            "overridden": (
                settings.enabled
                and existing_spool is not None
                and used_spool != existing_spool
            ),
            "reason": self._spool_reason(
                settings=settings,
                existing_spool=existing_spool,
                existing_spool_valid=existing_spool_valid,
                used_spool=used_spool,
            ),
        }

    def _spool_reason(
        self,
        *,
        settings: SpoolSettings,
        existing_spool: Path | None,
        existing_spool_valid: bool,
        used_spool: Path | None,
    ) -> str:
        """
        Determine why the selected spool was used.
        """

        if not settings.enabled:

            if existing_spool is not None:
                return "spool_management_disabled"

            return "disabled"

        if existing_spool is None:

            return "spool_created"

        if settings.override:

            return "override_requested"

        if not existing_spool_valid:

            return "existing_spool_invalid"

        return "existing_spool_valid"
