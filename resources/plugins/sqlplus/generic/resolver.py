"""
SQLPlus execution input resolution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import GenericPluginError

from .model import SqlPlusExecution


class SqlPlusResolver:
    """
    Resolve direct and execution-plan inputs into SQLPlus executions.
    """

    def resolve_direct(
        self,
        executions: Any,
    ) -> list[SqlPlusExecution]:
        """
        Resolve direct execution definitions.
        """

        if not isinstance(executions, list):
            raise GenericPluginError(
                "'executions' must be a list.",
            )

        if not executions:
            raise GenericPluginError(
                "'executions' must not be empty.",
            )

        result: list[SqlPlusExecution] = []

        for index, execution in enumerate(executions):

            if not isinstance(execution, dict):
                raise GenericPluginError(
                    f"Execution {index + 1} must be an object.",
                )

            result.append(
                self._build_execution(
                    execution,
                    context=f"execution {index + 1}",
                )
            )

        return result

    def resolve_plan(
        self,
        *,
        connection: Any,
        schemas: Any,
        execution_plan: Any,
        scripts: Any,
    ) -> list[SqlPlusExecution]:
        """
        Resolve BuildReleaseContext database information.
        """

        connection_data = self._validate_connection(
            connection,
        )

        schema_data = self._validate_schemas(
            schemas,
        )

        applications = self._validate_execution_plan(
            execution_plan,
        )

        script_data = self._validate_scripts(
            scripts,
        )

        result: list[SqlPlusExecution] = []

        for application, definition in applications.items():

            schema = definition.get(
                "schema",
            )

            calling_script = definition.get(
                "calling_script",
            )

            if not isinstance(schema, str) or not schema.strip():
                raise GenericPluginError(
                    f"Schema is missing for application "
                    f"'{application}'.",
                )

            schema = schema.strip()

            if not isinstance(
                calling_script,
                str,
            ) or not calling_script.strip():
                raise GenericPluginError(
                    f"Calling script is missing for application "
                    f"'{application}'.",
                )

            credentials = schema_data.get(
                schema,
            )

            if not isinstance(credentials, dict):
                raise GenericPluginError(
                    f"Schema credentials not found for "
                    f"schema '{schema}'.",
                )

            username = credentials.get(
                "username",
            )

            password = credentials.get(
                "password",
            )

            if not isinstance(
                username,
                str,
            ) or not username:
                raise GenericPluginError(
                    f"Username is missing for schema "
                    f"'{schema}'.",
                )

            if not isinstance(
                password,
                str,
            ):
                raise GenericPluginError(
                    f"Password is missing for schema "
                    f"'{schema}'.",
                )

            script = self._find_script(
                scripts=script_data,
                application=application,
                calling_script=calling_script,
            )

            if script is None:
                raise GenericPluginError(
                    f"Calling script '{calling_script}' for "
                    f"application '{application}' was not found.",
                )

            result.append(
                SqlPlusExecution(
                    ip=connection_data["ip"],
                    port=connection_data["port"],
                    sid=connection_data["sid"],
                    schema=schema,
                    username=username,
                    password=password,
                    script=script,
                )
            )

        if not result:
            raise GenericPluginError(
                "Execution plan contains no applications.",
            )

        return result

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_connection(
        connection: Any,
    ) -> dict[str, Any]:

        if not isinstance(connection, dict):
            raise GenericPluginError(
                "'connection' must be an object.",
            )

        ip = connection.get("IP")
        port = connection.get("PORT")
        sid = connection.get("SID")

        if not isinstance(ip, str) or not ip.strip():
            raise GenericPluginError(
                "Connection 'IP' must be a non-empty string.",
            )

        if isinstance(port, bool) or not isinstance(port, int):
            raise GenericPluginError(
                "Connection 'PORT' must be an integer.",
            )

        if not 1 <= port <= 65535:
            raise GenericPluginError(
                "Connection 'PORT' must be between 1 and 65535.",
            )

        if not isinstance(sid, str) or not sid.strip():
            raise GenericPluginError(
                "Connection 'SID' must be a non-empty string.",
            )

        return {
            "ip": ip.strip(),
            "port": port,
            "sid": sid.strip(),
        }

    @staticmethod
    def _validate_schemas(
        schemas: Any,
    ) -> dict[str, Any]:

        if not isinstance(schemas, dict):
            raise GenericPluginError(
                "'schemas' must be an object.",
            )

        if not schemas:
            raise GenericPluginError(
                "'schemas' must not be empty.",
            )

        return schemas

    @staticmethod
    def _validate_execution_plan(
        execution_plan: Any,
    ) -> dict[str, Any]:

        if not isinstance(execution_plan, dict):
            raise GenericPluginError(
                "'execution_plan' must be an object.",
            )

        applications = execution_plan.get(
            "applications",
        )

        if not isinstance(applications, dict):
            raise GenericPluginError(
                "'execution_plan.applications' must be an object.",
            )

        if not applications:
            raise GenericPluginError(
                "'execution_plan.applications' must not be empty.",
            )

        for application, definition in applications.items():

            if not isinstance(application, str) or not application:
                raise GenericPluginError(
                    "Execution-plan application name must be "
                    "a non-empty string.",
                )

            if not isinstance(definition, dict):
                raise GenericPluginError(
                    f"Execution-plan entry for '{application}' "
                    "must be an object.",
                )

        return applications

    @staticmethod
    def _validate_scripts(
        scripts: Any,
    ) -> list[dict[str, Any]]:

        if not isinstance(scripts, list):
            raise GenericPluginError(
                "'scripts' must be a list.",
            )

        if not scripts:
            raise GenericPluginError(
                "'scripts' must not be empty.",
            )

        for index, script in enumerate(scripts):

            if not isinstance(script, dict):
                raise GenericPluginError(
                    f"Script entry {index + 1} must be an object.",
                )

            application = script.get(
                "application",
            )

            path = script.get(
                "script",
            )

            if not isinstance(
                application,
                str,
            ) or not application.strip():
                raise GenericPluginError(
                    f"Script entry {index + 1} has an invalid "
                    "'application'.",
                )

            if not isinstance(
                path,
                str,
            ) or not path.strip():
                raise GenericPluginError(
                    f"Script entry {index + 1} has an invalid "
                    "'script'.",
                )

        return scripts

    @staticmethod
    def _find_script(
        *,
        scripts: list[dict[str, Any]],
        application: str,
        calling_script: str,
    ) -> Path | None:

        expected_name = Path(
            calling_script,
        ).name

        for entry in scripts:

            entry_application = entry.get(
                "application",
            )

            entry_script = entry.get(
                "script",
            )

            if (
                entry_application != application
                or not isinstance(entry_script, str)
            ):
                continue

            path = Path(
                entry_script,
            )

            if path.name == expected_name:
                return path

        return None

    # ------------------------------------------------------------------
    # Direct execution
    # ------------------------------------------------------------------

    def _build_execution(
        self,
        execution: dict[str, Any],
        *,
        context: str,
    ) -> SqlPlusExecution:

        ip = execution.get("ip")
        port = execution.get("port")
        sid = execution.get("sid")
        schema = execution.get("schema")
        username = execution.get("username")
        password = execution.get("password")
        script = execution.get("script")

        if not isinstance(ip, str) or not ip.strip():
            raise GenericPluginError(
                f"{context}: 'ip' must be a non-empty string.",
            )

        if isinstance(port, bool) or not isinstance(port, int):
            raise GenericPluginError(
                f"{context}: 'port' must be an integer.",
            )

        if not 1 <= port <= 65535:
            raise GenericPluginError(
                f"{context}: 'port' must be between 1 and 65535.",
            )

        if not isinstance(sid, str) or not sid.strip():
            raise GenericPluginError(
                f"{context}: 'sid' must be a non-empty string.",
            )

        if not isinstance(schema, str) or not schema.strip():
            raise GenericPluginError(
                f"{context}: 'schema' must be a non-empty string.",
            )

        if not isinstance(username, str) or not username:
            raise GenericPluginError(
                f"{context}: 'username' must be a non-empty string.",
            )

        if not isinstance(password, str):
            raise GenericPluginError(
                f"{context}: 'password' is required.",
            )

        if not isinstance(script, str) or not script.strip():
            raise GenericPluginError(
                f"{context}: 'script' must be a non-empty path.",
            )

        script_path = Path(script).expanduser()

        if not script_path.is_file():
            raise GenericPluginError(
                f"{context}: SQL script does not exist: "
                f"{script_path}",
            )

        return SqlPlusExecution(
            ip=ip.strip(),
            port=port,
            sid=sid.strip(),
            schema=schema.strip(),
            username=username,
            password=password,
            script=script_path.resolve(),
        )

    @staticmethod
    def validate_on_error(
        on_error: Any,
    ) -> str:
        """
        Validate the execution error policy.
        """

        if not isinstance(on_error, str):
            raise GenericPluginError(
                "'on_error' must be either 'abort' or 'continue'.",
            )

        value = on_error.strip().casefold()

        if value not in {
            "abort",
            "continue",
        }:
            raise GenericPluginError(
                "'on_error' must be either 'abort' or 'continue'.",
            )

        return value
