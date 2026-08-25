"""
SQLPlus plugin.
"""

from __future__ import annotations

from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import GenericPluginException
from .executor import SqlPlusExecutor
from .resolver import SqlPlusResolver


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

        with self.activity(
            "sqlplus",
        ):
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
            raise GenericPluginException(
                "'mode' is required.",
            )

        mode = mode.strip().casefold()

        on_error = SqlPlusResolver.validate_on_error(
            self.arguments.get(
                "on_error",
                "abort",
            ),
        )

        resolver = SqlPlusResolver()

        if mode == "plan":

            execution = self.arguments.get(
                "execution",
            )

            if not isinstance(execution, dict):
                raise GenericPluginException(
                    "'execution' must be an object in plan mode.",
                )

            executions = resolver.resolve_plan(
                connection=self.arguments.get(
                    "connection",
                ),
                schemas=self.arguments.get(
                    "schemas",
                ),
                execution_plan=execution.get(
                    "execution_plan",
                ),
                scripts=execution.get(
                    "scripts",
                ),
            )

        elif mode == "direct":

            executions = resolver.resolve_direct(
                self.arguments.get(
                    "executions",
                ),
            )

        else:

            raise GenericPluginException(
                f"Unsupported SQLPlus mode: '{mode}'.",
            )

        executor = SqlPlusExecutor(
            shell=self.shell,
        )

        results = executor.execute_all(
            executions,
            on_error=on_error,
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
                    }
                    for result in results
                ],
            },
        )

        return changes, errors
