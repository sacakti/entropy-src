"""
Environment operations mixin.

Provides access to environment variables and host information.
"""

from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path

from lib.executor.types import Command, PathLike


class EnvironmentMixin:
    """
    Provides environment operations.
    """

    def getenv(
        self,
        name: str,
        default: str | None = None,
    ) -> str | None:
        """
        Return the value of an environment variable.

        Parameters
        ----------
        name:
            Environment variable name.

        default:
            Value returned if the variable does not exist.
        """

        return os.getenv(name, default)

    def setenv(
        self,
        name: str,
        value: str,
    ) -> None:
        """
        Set an environment variable for the current process.
        """

        os.environ[name] = value

    def which(
        self,
        command: Command,
    ) -> Path | None:
        """
        Locate an executable in PATH.

        Parameters
        ----------
        command:
            Executable name.

        Returns
        -------
        str | None
            Absolute executable path or None.
        """

        executable = shutil.which(command)

        if executable is None:
            return None

        return Path(executable)

    def hostname(self) -> str:
        """
        Return the system hostname.
        """

        return socket.gethostname()

    def expandvars(
        self,
        path: PathLike,
    ) -> Path:
        """
        Expand environment variables.

        Example
        -------
        "$HOME/releases"
            ->
        "/home/oracle/releases"
        """

        return Path(
            os.path.expandvars(str(path))
        )