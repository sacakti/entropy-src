"""
SQLPlus plugin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from pathlib import Path

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import GenericPluginError
from .executor import SqlPlusExecutor
from .resolver import SqlPlusResolver
from .spool.resolver import SpoolSettingsResolver

if TYPE_CHECKING:
    from .model import SqlPlusExecutionResult

class GenericPlugin(
    BasePlugin,
):
    """
    SQLPlus plugin implementation.
    """

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute SQLPlus operations.
        """

        self.message.info(
            "Starting SQLPlus.",
        )

        changes: list[dict[str, Any]]
        errors: list[dict[str, Any]]

        changes, errors = self._execute()

        success = bool(
            self.outputs.get(
                "success",
                False,
            ),
        )

        if success:
            self.message.success(
                "SQLPlus completed successfully.",
            )
        else:
            self.message.error(
                "SQLPlus execution failed.",
            )

        return PluginResult(
            success=success,
            changed=bool(
                self.outputs.get(
                    "succeeded",
                    0,
                ),
            ),
            outputs=dict(
                self.outputs,
            ),
            changes=changes,
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
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """
        Resolve and execute SQLPlus operations.
        """

        sqlhome = self.arguments.path(
            "sqlhome",
            None
        )

        mode = self.arguments.string(
            "mode",
            None
        )

        if not mode:
            raise GenericPluginError(
                "'mode' is required.",
            )

        mode = mode.strip().casefold()

        on_error = SqlPlusResolver.validate_on_error(
            self.arguments.get(
                "on_error",
                "abort",
            ),
        )

        spool_settings = SpoolSettingsResolver().resolve(
            self.arguments.dictionary(
                "spool",
            ),
        )

        resolver = SqlPlusResolver()

        if mode == "plan":

            execution = self.arguments.dictionary(
                "execution",
            )


            execution_plan = execution.get(
                "execution_plan",
            )

            scripts = execution.get(
                "scripts",
            )

            if execution_plan is None:
                self.message.info(
                    "No SQL execution plan found. Skipping SQLPlus.",
                )

                self.outputs.update(
                    {
                        "success": True,
                        "mode": mode,
                        "on_error": on_error,
                        "executions": 0,
                        "succeeded": 0,
                        "failed": 0,
                        "skipped": 0,
                        "results": [],
                    },
                )

                return [], []

            executions = resolver.resolve_plan(
                connection=self.arguments.get(
                    "connection",
                ),
                schemas=self.arguments.get(
                    "schemas",
                ),
                execution_plan=execution_plan,
                scripts=scripts,
            )

        elif mode == "direct":

            executions = resolver.resolve_direct(
                self.arguments.get(
                    "executions",
                ),
            )

        else:

            raise GenericPluginError(
                f"Unsupported SQLPlus mode: '{mode}'.",
            )

        executor = SqlPlusExecutor(
            shell=self.shell,
            activity=self.activity,
            message=self.message,
        )

        execution_path = self.arguments.path(
            "execution_path",
        )

        release_value = self.arguments.string(
            "release",
            "release",
        )

        if (
            spool_settings.enabled
            and execution_path is None
        ):

            if not executions:
                raise GenericPluginError(
                    "'execution_path' cannot be resolved because "
                    "there are no SQL executions.",
                )

            execution_path = executions[0].script.parent

        results = executor.execute_all(
            sqlhome,
            executions,
            on_error=on_error,
            spool_settings=spool_settings,
            execution_path=execution_path,
            release=release_value,
        )

        changes: list[dict[str, Any]] = []

        for result in results:

            self._log_execution_output(
                result,
            )

            if result.success:

                changes.append(
                    {
                        "schema": result.schema,
                        "script": str(result.script),
                        "executed_script": str(result.executed_script),
                        "action": "execute",
                        "status": "executed",
                    },
                )

            else:

                changes.append(
                    {
                        "schema": result.schema,
                        "script": str(result.script),
                         "executed_script": str(result.executed_script),
                        "action": "execute",
                        "status": "failed",
                    },
                )

        succeeded = sum(
            result.success
            for result in results
        )

        failed = len(results) - succeeded

        skipped = (
            len(executions)
            - len(results)
        )

        success = (
            failed == 0
            and skipped == 0
        )

        errors = [
            {
                "schema": result.schema,
                "script": str(result.script),
                "exit_code": result.exit_code,
                "type": result.error_type,
                "message": result.error_message,
                "stderr": result.stderr,
                "spool": result.spool.get("used"),
            }
            for result in results
            if not result.success
        ]

        self.outputs.update(
            {
                "success": success,
                "mode": mode,
                "on_error": on_error,
                "executions": len(executions),
                "succeeded": succeeded,
                "failed": failed,
                "skipped": skipped,
                "results": [
                    {
                        "schema": result.schema,
                        "script": str(result.script),
                        "success": result.success,
                        "exit_code": result.exit_code,
                        "stdout": self._stdout_summary(
                            result.stdout,
                        ),
                        "stderr": result.stderr,
                        "duration": result.duration,
                        "spool": result.spool,
                        "error_type": result.error_type,
                        "error_message": result.error_message,
                    }
                    for result in results
                ],
            },
        )

        for result in results:

            if not result.spool:
                continue

            spool_path = result.spool.get(
                "used",
            )

            if not isinstance(
                spool_path,
                str,
            ) or not spool_path.strip():
                continue

            self.artifacts[
                f"sqlplus_{result.schema}_{result.script.stem}_spool"
            ] = Path(spool_path)

        return changes, errors

    @staticmethod
    def _stdout_summary(
        stdout: str,
        *,
        max_lines: int = 5,
    ) -> dict[str, Any]:
        """
        Create a concise SQLPlus stdout representation.
        """

        if not stdout:
            return {
                "preview": "",
                "lines": 0,
                "truncated": False,
            }

        lines = stdout.splitlines()
        line_count = len(lines)

        if line_count <= max_lines:
            return {
                "preview": stdout,
                "lines": line_count,
                "truncated": False,
            }

        preview = "\n".join(
            lines[:max_lines],
        )

        return {
            "preview": (
                f"{preview}\n"
                "... (stdout is large; see spool log)"
            ),
            "lines": line_count,
            "truncated": True,
        }

    def _log_execution_output(
        self,
        result: SqlPlusExecutionResult,
    ) -> None:
        """
        Log SQLPlus execution output when no spool is available.
        """

        if result.spool is not None:
            return

        if not result.stdout.strip():
            return

        self.log.info(
            (
                f"SQLPlus output: "
                f"{result.schema}/{result.script.name}\n"
                f"{result.stdout}"
            ),
        )
