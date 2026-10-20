"""
Launcher installer.

Creates and removes the Entropy command launcher.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

from lib.install.paths import InstallerPathManager

from .platform import Platform


class Launcher:

    def __init__(
        self,
        platform,
        paths: InstallerPathManager,
        python: Path | None = None,
    ) -> None:

        self._platform = platform
        self._paths = paths
        # The runtime Python (bundled or chosen at install time).
        self._python = python or Path(sys.executable)

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def install(self):

        launcher = self._launcher_path()

        launcher.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        launcher.write_text(
            self._script(),
            encoding="utf-8",
        )

        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)

        return launcher

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def uninstall(self):

        launcher = self._launcher_path()

        if launcher.exists():

            launcher.unlink()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _launcher_path(self) -> Path:

        if self._platform == Platform.WINDOWS:

            return self._paths.launcher_windows

        return self._paths.launcher_unix

    def _script(self) -> str:

        entropy = self._paths.installed_application

        if self._platform == Platform.WINDOWS:

            return "@echo off\n" f'"{self._python}" ' f'"{entropy}" %*\n'

        return "#!/usr/bin/env bash\n\n" f'exec "{self._python}" ' f'"{entropy}" "$@"\n'
