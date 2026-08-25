"""
SQLPlus command execution.
"""

from __future__ import annotations

import re
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.executor.result import ExecutionResult

from .model import SqlPlusExecution, SqlPlusExecutionResult

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
    ) -> None:
        self._shell = shell

    @staticmethod
    def build_command(
        execution: SqlPlusExecution,
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

        command = [
            "sqlplus",
            connection,
            f"@{execution.script}",
        ]

        display_command = [
            "sqlplus",
            safe_connection,
            f"@{execution.script}",
        ]

        return command, display_command

    def execute(
        self,
        execution: SqlPlusExecution,
        *,
        timeout: int | None = None,
    ) -> SqlPlusExecutionResult:
        """
        Execute one SQLPlus script.
        """

        command, display_command = self.build_command(
            execution,
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
            )

        return self.interpret_result(
            execution,
            result,
        )

    def execute_all(
        self,
        executions: list[SqlPlusExecution],
        *,
        on_error: str,
        timeout: int | None = None,
    ) -> list[SqlPlusExecutionResult]:
        """
        Execute multiple SQLPlus scripts according to the error policy.
        """

        results: list[SqlPlusExecutionResult] = []

        for execution in executions:

            result = self.execute(
                execution,
                timeout=timeout,
            )

            results.append(
                result,
            )

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
    ) -> SqlPlusExecutionResult:

        output = (
            f"{result.stdout}\n"
            f"{result.stderr}"
        )

        sqlplus_error = (
            result.exit_code != 0
            or SqlPlusExecutor._contains_sqlplus_error(
                output,
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
        )
