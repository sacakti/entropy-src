"""
Generic OpenShift operations plugin.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import GenericPluginException


class GenericPlugin(BasePlugin):
    """
    Execute generic OpenShift CLI operations.

    Supported operations:

    - login
    - logout
    - project
    - whoami
    - get
    - create
    - apply
    - replace
    - delete
    - raw
    """

    SUPPORTED_OPERATIONS = (
        "login",
        "logout",
        "project",
        "whoami",
        "get",
        "create",
        "apply",
        "replace",
        "delete",
        "raw",
    )

    ENVIRONMENT_PATTERN = re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )

    KUBECONFIG_DIRECTORY = ".kube"

    KUBECONFIG_FILENAME = "config"

    def execute(self) -> PluginResult:
        """
        Execute the requested OpenShift operation.
        """

        self.message.info(
            "Starting OpenShift operation.",
        )

        try:

            result = self._execute()

        except GenericPluginException as exc:

            self.log.error(
                str(exc),
            )

            self.message.error(
                str(exc),
            )

            return self._failure(
                str(exc),
            )

        if result.success:

            self.message.success(
                "OpenShift operation completed successfully.",
            )

        else:

            self.message.error(
                "OpenShift operation failed.",
            )

        return result

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _execute(self) -> PluginResult:
        """
        Dispatch the requested OpenShift operation.
        """

        operations = self.arguments.get("operations")
        operation = self.arguments.get("operation")
        resources = self.arguments.get("resources")

        if operations is not None:

            if operation is not None or resources is not None:
                raise GenericPluginException(
                    "Arguments 'operations' cannot be combined with "
                    "'operation' or 'resources'.",
                )

            return self._operations(
                operations,
            )

        if operation is None:

            raise GenericPluginException(
                "Either 'operations' or 'operation' must be specified.",
            )

        if not isinstance(
            operation,
            str,
        ) or not operation.strip():

            raise GenericPluginException(
                "Argument 'operation' must be specified.",
            )

        operation = operation.strip().lower()

        if operation not in self.SUPPORTED_OPERATIONS:

            raise GenericPluginException(
                f"Unsupported OpenShift operation "
                f"'{operation}'. Supported operations: "
                f"{', '.join(self.SUPPORTED_OPERATIONS)}.",
            )

        if operation == "login":
            return self._login()

        if operation == "logout":
            return self._logout()

        if operation == "project":
            return self._project()

        if operation == "whoami":
            return self._whoami()

        if operation == "get":
            return self._resource_operation("get")

        if operation == "create":
            return self._resource_operation("create")

        if operation == "apply":
            return self._resource_operation("apply")

        if operation == "replace":
            return self._resource_operation("replace")

        if operation == "delete":
            return self._resource_operation("delete")

        return self._raw()

    # ------------------------------------------------------------------
    # Kubeconfig
    # ------------------------------------------------------------------

    def _environment(
        self,
    ) -> str:
        """
        Resolve and validate the OpenShift environment name.
        """

        environment = self.arguments.get(
            "environment",
        )

        if not isinstance(
            environment,
            str,
        ) or not environment.strip():

            raise GenericPluginException(
                "Argument 'environment' must be a "
                "non-empty string.",
            )

        environment = environment.strip()

        if not self.ENVIRONMENT_PATTERN.fullmatch(
            environment,
        ):

            raise GenericPluginException(
                "Argument 'environment' contains invalid "
                "characters. Use only letters, numbers, '.', "
                "'_' and '-'.",
            )

        return environment

    def _kubeconfig_directory(
        self,
        environment: str,
    ) -> Path:
        """
        Return the environment-specific kubeconfig directory.
        """

        return (
            self.session_directory
            / self.KUBECONFIG_DIRECTORY
            / environment
        )

    def _kubeconfig(
        self,
        environment: str,
        *,
        create: bool = False,
    ) -> Path:
        """
        Resolve the environment-specific kubeconfig.

        When create is True, the directory is created.
        """

        directory = self._kubeconfig_directory(
            environment,
        )

        if create:

            try:

                self.filesystem.mkdir(
                    directory,
                    parents=True,
                    exist_ok=True,
                )

            except (OSError, ValueError) as exc:

                raise GenericPluginException(
                    "Unable to create OpenShift kubeconfig "
                    f"directory '{directory}': {exc}",
                ) from exc

        path = (
            directory
            / self.KUBECONFIG_FILENAME
        )

        if not create and not self.filesystem.exists(
            path,
        ):

            raise GenericPluginException(
                f"No OpenShift session exists for environment "
                f"'{environment}'. Run the login operation first.",
            )

        return path

    def _remove_kubeconfig(
        self,
        kubeconfig: Path,
    ) -> None:
        """
        Remove an environment-specific kubeconfig.
        """

        if not self.filesystem.exists(
            kubeconfig,
        ):

            return

        try:

            self.filesystem.remove(
                kubeconfig,
            )

        except OSError as exc:

            raise GenericPluginException(
                f"Unable to remove OpenShift kubeconfig "
                f"'{kubeconfig}': {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # OpenShift command
    # ------------------------------------------------------------------

    def _oc(
        self,
        command: list[str],
        *,
        kubeconfig: Path,
    ) -> Any:
        """
        Execute an OpenShift command using an isolated kubeconfig.
        """

        full_command = [
            "oc",
            *command,
        ]

        self.log.debug(
            "Executing OpenShift command: "
            + " ".join(
                full_command,
            ),
        )

        try:

            result = self.shell.run(
                full_command,
                env={
                    "KUBECONFIG": str(
                        kubeconfig,
                    ),
                },
            )

        except FileNotFoundError as exc:

            raise GenericPluginException(
                "OpenShift CLI 'oc' was not found. "
                "Please install the OpenShift CLI and ensure "
                "it is available in PATH.",
            ) from exc

        except OSError as exc:

            raise GenericPluginException(
                f"Unable to execute OpenShift CLI: {exc}",
            ) from exc

        self._log_result(
            result,
        )

        return result

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _login(self) -> PluginResult:
        """
        Login to an OpenShift environment.

        A dedicated kubeconfig is created for the environment.
        """

        environment = self._environment()

        api_url = self.arguments.string(
            "api_url",
        )

        username = self.arguments.string(
            "username",
        )

        password = self.arguments.string(
            "password",
        )

        insecure_skip_tls_verify = self.arguments.boolean(
            "insecure_skip_tls_verify",
            default=False,
        )

        kubeconfig = self._kubeconfig(
            environment,
            create=True,
        )

        self.message.info(
            f"Logging into OpenShift environment "
            f"'{environment}' at '{api_url}'.",
        )

        command = [
            "login",
            api_url,
            "--username",
            username,
            "--password",
            password,
        ]

        if insecure_skip_tls_verify:

            command.append(
                "--insecure-skip-tls-verify",
            )

        result = self._oc(
            command,
            kubeconfig=kubeconfig,
        )

        if result.failed:

            try:

                self._remove_kubeconfig(
                    kubeconfig,
                )

            except GenericPluginException as exc:

                self.log.warning(
                    str(exc),
                )

            return self._failure(
                result.stderr
                or (
                    "OpenShift login failed "
                    f"for environment '{environment}'."
                ),
            )

        self.outputs.update(
            {
                "operation": "login",
                "environment": environment,
                "api_url": api_url,
                "success": True,
                "kubeconfig": str(kubeconfig),
                "exit_code": result.exit_code,
            },
        )

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def _logout(self) -> PluginResult:
        """
        Logout from an OpenShift environment and remove its kubeconfig.
        """

        environment = self._environment()

        kubeconfig = self._kubeconfig(
            environment,
        )

        result = self._oc(
            [
                "logout",
            ],
            kubeconfig=kubeconfig,
        )

        if result.failed:

            return self._failure(
                result.stderr
                or (
                    "OpenShift logout failed "
                    f"for environment '{environment}'."
                ),
            )

        self._remove_kubeconfig(
            kubeconfig,
        )

        self.outputs.update(
            {
                "operation": "logout",
                "environment": environment,
                "success": True,
                "exit_code": result.exit_code,
            },
        )

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Project
    # ------------------------------------------------------------------

    def _project(self) -> PluginResult:
        """
        Display or switch the current OpenShift project.
        """

        environment = self._environment()

        namespace = self.arguments.get(
            "namespace",
        )

        kubeconfig = self._kubeconfig(
            environment,
        )

        if namespace is None:

            result = self._oc(
                [
                    "project",
                ],
                kubeconfig=kubeconfig,
            )

            self.outputs.update(
                {
                    "operation": "project",
                    "environment": environment,
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                },
            )

            if result.failed:

                return self._failure(
                    result.stderr
                    or (
                        "Unable to determine current "
                        "OpenShift project."
                    ),
                )

            return self._success(
                changed=False,
            )

        if not isinstance(
            namespace,
            str,
        ) or not namespace.strip():

            raise GenericPluginException(
                "Argument 'namespace' must be a "
                "non-empty string.",
            )

        namespace = namespace.strip()

        result = self._oc(
            [
                "project",
                namespace,
            ],
            kubeconfig=kubeconfig,
        )

        self.outputs.update(
            {
                "operation": "project",
                "environment": environment,
                "namespace": namespace,
                "success": result.success,
                "exit_code": result.exit_code,
            },
        )

        if result.failed:

            return self._failure(
                result.stderr
                or (
                    f"Unable to switch to OpenShift "
                    f"project '{namespace}'."
                ),
            )

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Whoami
    # ------------------------------------------------------------------

    def _whoami(self) -> PluginResult:
        """
        Return the authenticated OpenShift user.
        """

        environment = self._environment()

        kubeconfig = self._kubeconfig(
            environment,
        )

        result = self._oc(
            [
                "whoami",
            ],
            kubeconfig=kubeconfig,
        )

        username = result.stdout.strip()

        self.outputs.update(
            {
                "operation": "whoami",
                "environment": environment,
                "username": username,
                "success": result.success,
                "exit_code": result.exit_code,
            },
        )

        if result.failed:

            return self._failure(
                result.stderr
                or (
                    "Unable to determine current "
                    "OpenShift user."
                ),
            )

        return self._success(
            changed=False,
        )

    # ------------------------------------------------------------------
    # Resource operations
    # ------------------------------------------------------------------

    def _resource_operation(
        self,
        operation: str,
    ) -> PluginResult:
        """
        Execute a single OpenShift resource operation.

        ``resource`` may be either a single resource path or
        a list of resource paths.

        Each resource is executed independently.
        """

        environment = self._environment()

        resources = self.arguments.get(
            "resources",
        )

        arguments = self.arguments.get(
            "arguments",
            [],
        )

        resources = self._normalize_resources(
            resources,
        )

        self._validate_arguments(
            arguments,
        )

        kubeconfig = self._kubeconfig(
            environment,
        )

        return self._execute_resources(
            operation=operation,
            resources=resources,
            arguments=arguments,
            environment=environment,
            kubeconfig=kubeconfig,
        )

    def _operations(
        self,
        operations: Any,
    ) -> PluginResult:
        """
        Execute multiple OpenShift resource operations.

        Operations are executed in the following order:

        create -> apply -> replace

        The ``operations`` argument must be a dictionary whose
        values are lists of resource paths.
        """

        if not isinstance(
            operations,
            dict,
        ):

            raise GenericPluginException(
                "Argument 'operations' must be a dictionary.",
            )

        supported_operations = (
            "create",
            "apply",
            "replace",
        )

        unknown_operations = set(
            operations,
        ) - set(
            supported_operations,
        )

        if unknown_operations:

            raise GenericPluginException(
                "Unsupported operation(s) in 'operations': "
                + ", ".join(
                    sorted(
                        unknown_operations,
                    ),
                )
                + ". Supported operations: "
                + ", ".join(
                    supported_operations,
                )
                + ".",
            )

        environment = self._environment()

        arguments = self.arguments.get(
            "arguments",
            [],
        )

        self._validate_arguments(
            arguments,
        )

        kubeconfig = self._kubeconfig(
            environment,
        )

        all_results: list[dict[str, Any]] = []

        failed_resources: list[str] = []

        changed = False

        executed_operations: dict[
            str,
            list[str],
        ] = {}

        for operation in supported_operations:

            resources = operations.get(
                operation,
                [],
            )

            if resources is None:
                continue

            normalized_resources = self._normalize_resources(
                resources,
                allow_empty=True,
            )

            if not normalized_resources:
                continue

            executed_operations[
                operation
            ] = list(
                normalized_resources,
            )

            result = self._execute_resources(
                operation=operation,
                resources=normalized_resources,
                arguments=arguments,
                environment=environment,
                kubeconfig=kubeconfig,
            )

            operation_results = result.outputs.get(
                "results",
                [],
            )

            if isinstance(
                operation_results,
                list,
            ):
                all_results.extend(
                    operation_results,
                )

            if result.changed:
                changed = True

            if not result.success:

                for item in operation_results:

                    if (
                        isinstance(
                            item,
                            dict,
                        )
                        and not item.get(
                            "success",
                            False,
                        )
                    ):

                        resource_path = item.get(
                            "resource",
                        )

                        if isinstance(
                            resource_path,
                            str,
                        ):
                            failed_resources.append(
                                resource_path,
                            )

        self.outputs.update(
            {
                "operation": "auto",
                "environment": environment,
                "operations": executed_operations,
                "results": all_results,
                "success": not failed_resources,
            },
        )

        if failed_resources:

            details = "; ".join(
                failed_resources,
            )

            return self._failure(
                "OpenShift automatic operation failed "
                f"for resource(s): {details}.",
            )

        return self._success(
            changed=changed,
        )

    def _execute_resources(
        self,
        *,
        operation: str,
        resources: list[str],
        arguments: list[str],
        environment: str,
        kubeconfig: Path,
    ) -> PluginResult:
        """
        Execute an OpenShift operation against multiple resources.

        Each resource is executed independently.
        """

        results: list[dict[str, Any]] = []

        failed_resources: list[str] = []

        changed = False

        for resource_path in resources:

            command = [
                operation,
                "-f",
                resource_path,
                *arguments,
            ]

            with self.activity(
                f"{operation} › {resource_path}",
            ):

                result = self._oc(
                    command,
                    kubeconfig=kubeconfig,
                )

            resource_result = {
                "operation": operation,
                "resource": resource_path,
                "exit_code": result.exit_code,
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration": result.duration,
            }

            results.append(
                resource_result,
            )

            if result.success:

                if operation in {
                    "create",
                    "apply",
                    "replace",
                    "delete",
                }:

                    changed = True

            else:

                failed_resources.append(
                    resource_path,
                )

        self.outputs.update(
            {
                "operation": operation,
                "environment": environment,
                "resources": list(resources),
                "results": results,
                "success": not failed_resources,
            },
        )

        if failed_resources:

            details = "; ".join(
                failed_resources,
            )

            return self._failure(
                f"OpenShift {operation} failed for "
                f"resource(s): {details}.",
            )

        return self._success(
            changed=changed,
        )

    # ------------------------------------------------------------------
    # Resource normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_resources(
        resource: Any,
        *,
        allow_empty: bool = False,
    ) -> list[str]:
        """
        Normalize a resource argument into a list.

        Supports both a single resource path and a list of
        resource paths.

        When ``allow_empty`` is True, an empty list is accepted.
        This is used by automatic operations where an operation
        may legitimately have no resources.
        """

        if isinstance(
            resource,
            str,
        ):

            if not resource.strip():

                raise GenericPluginException(
                    "Resource path must be a non-empty string.",
                )

            return [
                resource.strip(),
            ]

        if isinstance(
            resource,
            list,
        ):

            if not resource:

                if allow_empty:
                    return []

                raise GenericPluginException(
                    "Argument 'resource' must not be empty.",
                )

            resources: list[str] = []

            for item in resource:

                if (
                    not isinstance(
                        item,
                        str,
                    )
                    or not item.strip()
                ):

                    raise GenericPluginException(
                        "All values in 'resource' must be "
                        "non-empty strings.",
                    )

                resources.append(
                    item.strip(),
                )

            return resources

        raise GenericPluginException(
            "Argument 'resource' must be a string "
            "or a list of strings.",
        )

    # ------------------------------------------------------------------
    # Raw
    # ------------------------------------------------------------------

    def _raw(self) -> PluginResult:
        """
        Execute a raw OpenShift command.

        The command is supplied without the 'oc' prefix.
        """

        environment = self._environment()

        command = self.arguments.get(
            "command",
        )

        arguments = self.arguments.get(
            "arguments",
            [],
        )

        if not isinstance(
            command,
            str,
        ) or not command.strip():

            raise GenericPluginException(
                "Argument 'command' must be a non-empty string.",
            )

        self._validate_arguments(
            arguments,
        )

        kubeconfig = self._kubeconfig(
            environment,
        )

        oc_command = [
            command.strip(),
            *arguments,
        ]

        result = self._oc(
            oc_command,
            kubeconfig=kubeconfig,
        )

        self.outputs.update(
            {
                "operation": "raw",
                "environment": environment,
                "command": result.command,
                "exit_code": result.exit_code,
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration": result.duration,
            },
        )

        if result.failed:

            return self._failure(
                result.stderr
                or "OpenShift command failed.",
            )

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_arguments(
        arguments: Any,
    ) -> None:
        """
        Validate additional command arguments.
        """

        if not isinstance(
            arguments,
            list,
        ):

            raise GenericPluginException(
                "Argument 'arguments' must be a list.",
            )

        if not all(
            isinstance(
                argument,
                str,
            )
            for argument in arguments
        ):

            raise GenericPluginException(
                "All values in 'arguments' must be strings.",
            )

    # ------------------------------------------------------------------
    # Result helpers
    # ------------------------------------------------------------------

    def _success(
        self,
        *,
        changed: bool,
    ) -> PluginResult:
        """
        Create a successful result.
        """

        return PluginResult(
            success=True,
            changed=changed,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=[],
            warnings=[],
            metadata={
                "artifacts": {
                    name: str(path)
                    for name, path
                    in self.artifacts.items()
                },
            },
        )

    def _failure(
        self,
        error: str,
    ) -> PluginResult:
        """
        Create a failed result.
        """

        return PluginResult(
            success=False,
            changed=False,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=[
                error,
            ],
            warnings=[],
            metadata={
                "artifacts": {
                    name: str(path)
                    for name, path
                    in self.artifacts.items()
                },
            },
        )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_result(
        self,
        result: Any,
    ) -> None:
        """
        Log OpenShift command output.

        The command itself is already logged by _oc().
        Credentials are never written to the log intentionally.
        """

        if result.stdout:

            self.log.info(
                result.stdout,
            )

        if result.stderr:

            self.log.warning(
                result.stderr,
            )
