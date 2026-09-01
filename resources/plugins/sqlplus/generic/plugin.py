"""
SQLPlus plugin.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import GenericPluginError
from .executor import SqlPlusExecutor
from .resolver import SqlPlusResolver
from .spool.resolver import SpoolSettingsResolver

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

        mode = self.arguments.get(
            "mode",
        )

        if not isinstance(mode, str):
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
            self.arguments.get(
                "spool",
            ),
        )

        resolver = SqlPlusResolver()

        if mode == "plan":

            execution = self.arguments.get(
                "execution",
            )

            if not isinstance(execution, dict):
                raise GenericPluginError(
                    "'execution' must be an object in plan mode.",
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
        )

        execution_path_value = self.arguments.get(
            "execution_path",
        )

        execution_path = None

        if execution_path_value is not None:

            if not isinstance(
                execution_path_value,
                str,
            ):
                raise GenericPluginError(
                    "'execution_path' must be a string.",
                )

            if not execution_path_value.strip():
                raise GenericPluginError(
                    "'execution_path' must be a non-empty path.",
                )

            execution_path = Path(
                execution_path_value,
            )

        release_value = self.arguments.get(
            "release",
            "release",
        )

        if not isinstance(
            release_value,
            str,
        ):
            raise GenericPluginError(
                "'release' must be a string.",
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
            executions,
            on_error=on_error,
            spool_settings=spool_settings,
            execution_path=execution_path,
            release=release_value,
        )

        changes: list[dict[str, Any]] = []

        for result in results:

            if result.success:

                changes.append(
                    {
                        "schema": result.schema,
                        "script": str(result.script),
                        "action": "execute",
                        "status": "executed",
                    },
                )

            else:

                changes.append(
                    {
                        "schema": result.schema,
                        "script": str(result.script),
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
                "stderr": result.stderr,
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
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "duration": result.duration,
                        "spool": result.spool,
                    }
                    for result in results
                ],
            },
        )

        return changes, errors
