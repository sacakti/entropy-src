"""
Generic Docker operations plugin.
"""

from __future__ import annotations

import shutil
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import GenericPluginException


class GenericPlugin(
    BasePlugin,
):
    """
    Execute generic Docker operations.

    Supported operations:

    - login
    - pull
    - push
    - tag
    - inspect
    - raw
    """

    SUPPORTED_OPERATIONS = (
        "login",
        "pull",
        "push",
        "tag",
        "inspect",
        "raw",
    )

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the requested Docker operation.
        """

        self.message.info(
            "Starting Docker operation.",
        )

        try:

            with self.activity(
                "docker-generic",
            ):

                result = self._execute()

        except GenericPluginException as exc:

            self.message.error(
                str(exc),
            )

            return PluginResult(
                success=False,
                changed=False,
                outputs=dict(
                    self.outputs,
                ),
                changes=[],
                errors=[
                    str(exc),
                ],
                warnings=[],
                metadata={
                    "artifacts": {
                        name: str(path)
                        for name, path in self.artifacts.items()
                    },
                },
            )

        if result.success:

            self.message.success(
                "Docker operation completed successfully.",
            )

        else:

            self.message.error(
                "Docker operation failed.",
            )

        return result

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:
        """
        Dispatch the requested Docker operation.
        """

        self._ensure_docker()

        operation = self.arguments.get(
            "operation",
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
                f"Unsupported Docker operation '{operation}'. "
                f"Supported operations: "
                f"{', '.join(self.SUPPORTED_OPERATIONS)}.",
            )

        if operation == "login":

            return self._login()

        if operation == "pull":

            return self._images_operation(
                "pull",
            )

        if operation == "push":

            return self._images_operation(
                "push",
            )

        if operation == "tag":

            return self._tag()

        if operation == "inspect":

            return self._images_operation(
                "inspect",
            )

        return self._raw()

    # ------------------------------------------------------------------
    # Docker availability
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_docker() -> None:
        """
        Verify that Docker is available.
        """

        if shutil.which(
            "docker",
        ) is None:

            raise GenericPluginException(
                "Docker is not available on this system.",
            )

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _login(
        self,
    ) -> PluginResult:
        """
        Log in to a Docker registry.

        Username and password are optional. When both are supplied,
        the password is passed through stdin using --password-stdin.
        """

        registry = self.arguments.get(
            "registry",
        )

        username = self.arguments.get(
            "username",
        )

        password = self.arguments.get(
            "password",
        )

        self._validate_login(
            registry=registry,
            username=username,
            password=password,
        )

        command = [
            "docker",
            "login",
            registry,
        ]

        password_input: str | None = None

        if username is not None:

            command.extend(
                [
                    "--username",
                    username,
                    "--password-stdin",
                ],
            )

            password_input = password

        self.log.debug(
            "Executing Docker login for registry '%s'.",
            registry,
        )

        result = self.shell.run(
            command,
            input=password_input,
        )

        self._log_result(
            result,
        )

        self.outputs.update(
            {
                "operation": "login",
                "registry": registry,
                "success": result.success,
                "exit_code": result.exit_code,
            },
        )

        if not result.success:

            return self._failure(
                result.stderr
                or "Docker login failed.",
            )

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Pull / Push / Inspect
    # ------------------------------------------------------------------

    def _images_operation(
        self,
        operation: str,
    ) -> PluginResult:
        """
        Execute an operation against one or more images.
        """

        images = self.arguments.get(
            "images",
        )

        self._validate_images(
            images,
        )

        successful: list[str] = []
        failed: list[str] = []
        errors: list[str] = []

        changed = False

        for image in images:

            self.log.debug(
                "Executing Docker %s for image '%s'.",
                operation,
                image,
            )

            result = self.shell.run(
                [
                    "docker",
                    operation,
                    image,
                ],
            )

            self._log_result(
                result,
            )

            if result.success:

                successful.append(
                    image,
                )

                if operation in {
                    "pull",
                    "push",
                }:

                    changed = True

            else:

                failed.append(
                    image,
                )

                errors.append(
                    f"Docker {operation} failed for "
                    f"'{image}': "
                    f"{result.stderr or 'unknown error'}",
                )

        self.outputs.update(
            {
                "operation": operation,
                "successful": successful,
                "failed": failed,
                "total": len(images),
            },
        )

        if failed:

            return PluginResult(
                success=False,
                changed=changed,
                outputs=dict(
                    self.outputs,
                ),
                changes=[],
                errors=errors,
                warnings=[],
                metadata={
                    "artifacts": {},
                },
            )

        return self._success(
            changed=changed,
        )

    # ------------------------------------------------------------------
    # Tag
    # ------------------------------------------------------------------

    def _tag(
        self,
    ) -> PluginResult:
        """
        Tag a Docker image.
        """

        source = self.arguments.get(
            "source",
        )

        target = self.arguments.get(
            "target",
        )

        if not isinstance(
            source,
            str,
        ) or not source.strip():

            raise GenericPluginException(
                "Argument 'source' must be a non-empty string.",
            )

        if not isinstance(
            target,
            str,
        ) or not target.strip():

            raise GenericPluginException(
                "Argument 'target' must be a non-empty string.",
            )

        self.log.debug(
            "Tagging Docker image '%s' as '%s'.",
            source,
            target,
        )

        result = self.shell.run(
            [
                "docker",
                "tag",
                source,
                target,
            ],
        )

        self._log_result(
            result,
        )

        self.outputs.update(
            {
                "operation": "tag",
                "source": source,
                "target": target,
                "success": result.success,
                "exit_code": result.exit_code,
            },
        )

        if not result.success:

            return self._failure(
                result.stderr
                or f"Failed to tag '{source}'.",
            )

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Raw
    # ------------------------------------------------------------------

    def _raw(
        self,
    ) -> PluginResult:
        """
        Execute a raw Docker command.

        The command is supplied without the 'docker' prefix.
        """

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

        docker_command = [
            "docker",
            command,
            *arguments,
        ]

        self.log.debug(
            "Executing raw Docker command: %s",
            " ".join(
                docker_command,
            ),
        )

        result = self.shell.run(
            docker_command,
        )

        self._log_result(
            result,
        )

        self.outputs.update(
            {
                "operation": "raw",
                "command": result.command,
                "exit_code": result.exit_code,
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration": result.duration,
            },
        )

        if not result.success:

            return self._failure(
                result.stderr
                or "Docker command failed.",
            )

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_login(
        *,
        registry: Any,
        username: Any,
        password: Any,
    ) -> None:
        """
        Validate login arguments.
        """

        if not isinstance(
            registry,
            str,
        ) or not registry.strip():

            raise GenericPluginException(
                "Argument 'registry' must be a non-empty string.",
            )

        if username is None and password is None:

            return

        if username is None or password is None:

            raise GenericPluginException(
                "Arguments 'username' and 'password' "
                "must be provided together.",
            )

        if not isinstance(
            username,
            str,
        ) or not username.strip():

            raise GenericPluginException(
                "Argument 'username' must be a non-empty string.",
            )

        if not isinstance(
            password,
            str,
        ):

            raise GenericPluginException(
                "Argument 'password' must be a string.",
            )

    @staticmethod
    def _validate_images(
        images: Any,
    ) -> None:
        """
        Validate an image list.
        """

        if not isinstance(
            images,
            list,
        ):

            raise GenericPluginException(
                "Argument 'images' must be a list.",
            )

        if not images:

            raise GenericPluginException(
                "Argument 'images' must contain at least one image.",
            )

        if not all(
            isinstance(
                image,
                str,
            )
            and image.strip()
            for image in images
        ):

            raise GenericPluginException(
                "All values in 'images' must be non-empty strings.",
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
                "artifacts": {},
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
                "artifacts": {},
            },
        )

    def _log_result(
        self,
        result,
    ) -> None:
        """
        Log Docker command output.
        """

        if result.stdout:

            self.log.info(
                result.stdout,
            )

        if result.stderr:

            self.log.warning(
                result.stderr,
            )
