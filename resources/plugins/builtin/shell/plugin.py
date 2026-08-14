"""
Shell plugin.
"""

from __future__ import annotations

import shutil

import json

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import ShellException


class ShellPlugin(
    BasePlugin,
):
    """
    Execute shell commands or shell scripts.

    Workflow and Vault variable resolution are handled by the
    workflow engine before plugin execution.
    """

    DEFAULT_SHELLS = (
        "bash",
        "sh",
        "zsh",
    )

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the configured shell command or script.
        """

        self.message.info(
            "Starting plugin execution.",
        )

        with self.activity(
            "shell",
        ):

            self._execute()

        self.message.success(
            "Plugin completed successfully.",
        )

        return PluginResult(
            success=True,
            changed=True,
            outputs=dict(
                self.outputs,
            ),
            metadata={
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> None:
        """
        Execute the configured shell command or script.
        """

        command = self.arguments.get(
            "command",
        )

        if command is not None:

            command = self._stringify(
                command,
            )

        script = self.arguments.string(
            "script",
        )

        shell = self.arguments.string(
            "shell",
        )

        args = self.arguments.get(
            "args",
            [],
        )

        args = [
            self._stringify(
                value,
            )
            for value in args
        ]

        cwd = self.arguments.string(
            "cwd",
        )

        timeout = self.arguments.integer(
            "timeout",
        )

        env = self.arguments.dictionary(
            "env",
        )

        self._validate(
            command=command,
            script=script,
        )

        shell_path = self._resolve_shell(
            shell,
        )

        if command is not None:

            result = self._run_command(
                shell=shell_path,
                command=command,
                args=args,
                cwd=cwd,
                timeout=timeout,
                env=env,
            )

        else:

            assert script is not None

            result = self._run_script(
                shell=shell_path,
                script=script,
                args=args,
                cwd=cwd,
                timeout=timeout,
                env=env,
            )

        self._record_result(
            result,
        )

        if result.failed:

            raise ShellException(
                "Shell command failed with exit code " f"{result.exit_code}.",
            )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(
        *,
        command: str | None,
        script: str | None,
    ) -> None:
        """
        Validate ShellPlugin-specific arguments.
        """

        if command is None and script is None:

            raise ShellException(
                "Either 'command' or 'script' must be specified.",
            )

        if command is not None and script is not None:

            raise ShellException(
                "Only one of 'command' or 'script' may be specified.",
            )

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def _record_result(
        self,
        result,
    ) -> None:
        """
        Record shell execution results.
        """

        self.outputs["exit_code"] = result.exit_code
        self.outputs["success"] = result.success
        self.outputs["stdout"] = result.stdout
        self.outputs["stderr"] = result.stderr
        self.outputs["duration"] = result.duration

        if result.stdout:

            self.message.info(
                result.stdout,
            )

        if result.stderr:

            self.message.warning(
                result.stderr,
            )

    # ------------------------------------------------------------------
    # Command
    # ------------------------------------------------------------------

    def _run_command(
        self,
        shell: str,
        command: str,
        args: list,
        cwd: str | None,
        timeout: int | None,
        env: dict | None,
    ):
        """
        Execute an inline shell command.
        """

        process_arguments = [
            shell,
            "-c",
            command,
            "--",
            *args,
        ]

        self.log.info(
            f"Process arguments: {process_arguments!r}",
        )

        return self.shell.run(
            process_arguments,
            cwd=cwd,
            timeout=timeout,
            env=env,
        )

    # ------------------------------------------------------------------
    # Script
    # ------------------------------------------------------------------

    def _run_script(
        self,
        shell: str,
        script: str,
        args: list,
        cwd: str | None,
        timeout: int | None,
        env: dict | None,
    ):
        """
        Execute a shell script using the selected interpreter.
        """

        script_path = self.filesystem.path(
            script,
        )

        if not self.filesystem.exists(
            script_path,
        ):

            raise ShellException(
                f"Shell script '{script}' does not exist.",
            )

        return self.shell.run(
            [
                shell,
                str(script_path),
                *args,
            ],
            cwd=cwd,
            timeout=timeout,
            env=env,
        )

    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------

    def _resolve_shell(
        self,
        shell: str | None,
    ) -> str:
        """
        Resolve the shell executable.
        """

        if shell is not None:

            path = shutil.which(
                shell,
            )

            if path is None:

                raise ShellException(
                    f"Shell '{shell}' was not found on this system.",
                )

            self.message.info(
                f"Shell: {path}",
            )

            return path

        for candidate in self.DEFAULT_SHELLS:

            path = shutil.which(
                candidate,
            )

            if path is not None:

                return path

        raise ShellException(
            "No supported shell is available. "
            "Tried: "
            + ", ".join(
                self.DEFAULT_SHELLS,
            ),
        )

    @staticmethod
    def _stringify(
        value,
    ) -> str:
        """
        Convert a workflow value into a shell-safe string.
        """

        if isinstance(value, str):
            return value

        if isinstance(
            value,
            (dict, list),
        ):
            return json.dumps(
                value,
            )

        return str(value)
