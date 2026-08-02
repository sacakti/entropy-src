"""
Process execution mixin.

Provides methods for executing operating system commands.
"""

from __future__ import annotations

import os
import subprocess
import time
import shlex

from lib.executor.types import Command, Environment, PathLike

from .result import ExecutionResult


class ProcessMixin:
    """
    Provides operating system process execution.
    """

    def run(
        self,
        command: Command,
        cwd: PathLike | None = None,
        timeout: int | None = None,
        env: Environment | None = None,
        shell: bool = False,
        check: bool = False,
    ) -> ExecutionResult:
        """
        Execute a command.

        Parameters
        ----------
        command:
            Command to execute. Can be either a shell command string
            or a list of command arguments.

        cwd:
            Working directory for the process.

        timeout:
            Maximum execution time in seconds.

        env:
            Environment variables passed to the process.

        shell:
            Execute through the shell.

        check:
            Raise CalledProcessError if the command exits with
            a non-zero exit code.

        Returns
        -------
        ExecutionResult
            Complete execution details.
        """

        start = time.perf_counter()


        environment = os.environ.copy()

        if env:
            environment.update(env)

        process = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=environment,
            timeout=timeout,
            shell=shell,
            check=check,
            capture_output=True,
            text=True,
        )

        duration = time.perf_counter() - start

        # command_text = " ".join(map(str, command)) if isinstance(command, list) else command

        command_text = shlex.join(command)

        return ExecutionResult(
            command=command_text,
            success=(process.returncode == 0),
            exit_code=process.returncode,
            stdout=process.stdout.rstrip(),
            stderr=process.stderr.rstrip(),
            duration=duration,
        )

    def run_script(
        self,
        script: PathLike,
        *args: str,
        cwd: PathLike | None = None,
        timeout: int | None = None,
        env: Environment | None = None,
    ) -> ExecutionResult:
        """
        Execute a shell script.

        Parameters
        ----------
        script:
            Shell script to execute.

        args:
            Optional command-line arguments.

        cwd:
            Working directory.

        timeout:
            Maximum execution time.

        env:
            Environment variables.

        Returns
        -------
        ExecutionResult
            Complete execution details.
        """

        if not script.exists():
            raise FileNotFoundError(script)

        return self.run(
            command=[str(script), *map(str, args)],
            cwd=cwd,
            timeout=timeout,
            env=env,
        )

    def run_bash(
        self,
        command: str,
        cwd: PathLike | None = None,
        timeout: int | None = None,
        env: Environment | None = None,
    ) -> ExecutionResult:
        """
        Execute a command using the Bash shell.

        This is useful when shell features such as pipes,
        redirects, variable expansion or command substitution
        are required.

        Parameters
        ----------
        command:
            Bash command to execute.

        cwd:
            Working directory.

        timeout:
            Maximum execution time.

        env:
            Environment variables.

        Returns
        -------
        ExecutionResult
            Complete execution details.
        """

        return self.run(
            command=["/bin/bash", "-c", command],
            cwd=cwd,
            timeout=timeout,
            env=env,
        )
