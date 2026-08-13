"""
Shell plugin.
"""

from __future__ import annotations

import shutil
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin
from lib.plugins.exceptions import PluginException

class ShellPlugin(
    BasePlugin,
):
    """
    Execute shell commands or shell scripts.

    The plugin intentionally relies on the public Plugin SDK.

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

        try:

            with self.activity(
                "shell",
            ):

                self._execute()

        except Exception as exc:

            self.message.error(
                str(exc),
            )

            raise

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
    ) -> None:
        """
        Execute the configured shell command or script.
        """

        command = self.arguments.get(
            "command",
        )

        script = self.arguments.get(
            "script",
        )

        shell = self.arguments.get(
            "shell",
        )

        args = self.arguments.get(
            "args",
            [],
        )

        cwd = self.arguments.get(
            "cwd",
        )

        timeout = self.arguments.get(
            "timeout",
        )

        env = self.arguments.get(
            "env",
        )

        self._validate(
            command=command,
            script=script,
            shell=shell,
            args=args,
            cwd=cwd,
            timeout=timeout,
            env=env,
        )

        shell_path = self._resolve_shell(
            shell,
        )

        if shell:
            self.message.info(
                f"Shell: {shell_path}",
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

            result = self._run_script(
                shell=shell_path,
                script=script,
                args=args,
                cwd=cwd,
                timeout=timeout,
                env=env,
            )

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

        if result.failed:

            raise RuntimeError(
                f"Shell command failed with exit code "
                f"{result.exit_code}.",
            )

    # ------------------------------------------------------------------
    # Command
    # ------------------------------------------------------------------

    def _run_command(
        self,
        shell: str,
        command: str,
        args: list[str],
        cwd: str | None,
        timeout: int | None,
        env: dict[str, str] | None,
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
        args: list[str],
        cwd: str | None,
        timeout: int | None,
        env: dict[str, str] | None,
    ):
        """
        Execute a shell script using the selected interpreter.
        """

        script_path = self.filesystem.path(
            script,
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

        If no shell is supplied, the first available default
        shell is selected.
        """

        if shell is not None:

            shell = shell.strip()

            if not shell:

                shell = None

        if shell is not None:

            path = shutil.which(
                shell,
            )

            if path is None:

                raise PluginException(
                    f"Shell '{shell}' was not found on this system.",
                )

            return path

        for candidate in self.DEFAULT_SHELLS:

            path = shutil.which(
                candidate,
            )

            if path is not None:

                return path

        raise RuntimeError(
            "No supported shell is available. "
            "Tried: "
            + ", ".join(
                self.DEFAULT_SHELLS,
            ),
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(
        *,
        command: Any,
        script: Any,
        shell: Any,
        args: Any,
        cwd: Any,
        timeout: Any,
        env: Any,
    ) -> None:
        """
        Validate plugin arguments.
        """

        if command is None and script is None:

            raise PluginException(
                "Either 'command' or 'script' must be specified.",
            )

        if command is not None and script is not None:

            raise PluginException(
                "Only one of 'command' or 'script' may be specified.",
            )

        if command is not None:

            if not isinstance(
                command,
                str,
            ) or not command.strip():

                raise PluginException(
                    "Argument 'command' must be a non-empty string.",
                )

        if script is not None:

            if not isinstance(
                script,
                str,
            ) or not script.strip():

                raise PluginException(
                    "Argument 'script' must be a non-empty string.",
                )

        if shell is not None and not isinstance(
            shell,
            str,
        ):

            raise PluginException(
                "Argument 'shell' must be a string.",
            )

        if not isinstance(
            args,
            list,
        ):

            raise PluginException(
                "Argument 'args' must be a list.",
            )

        if not all(
            isinstance(
                argument,
                str,
            )
            for argument in args
        ):

            raise PluginException(
                "All values in 'args' must be strings.",
            )

        if cwd is not None and not isinstance(
            cwd,
            str,
        ):

            raise PluginException(
                "Argument 'cwd' must be a string.",
            )

        if timeout is not None:

            if not isinstance(
                timeout,
                int,
            ) or isinstance(
                timeout,
                bool,
            ):

                raise PluginException(
                    "Argument 'timeout' must be an integer.",
                )

            if timeout <= 0:

                raise PluginException(
                    "Argument 'timeout' must be greater than zero.",
                )

        if env is not None:

            if not isinstance(
                env,
                dict,
            ):

                raise PluginException(
                    "Argument 'env' must be a dictionary.",
                )

            if not all(
                isinstance(
                    key,
                    str,
                )
                and isinstance(
                    value,
                    str,
                )
                for key, value in env.items()
            ):

                raise PluginException(
                    "All environment variable names and values "
                    "must be strings.",
                )
