"""
Launcher installer.

Creates and removes the Entropy command launcher.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

from core.constants import APPLICATION_ROOT, LAUNCHER_DIR_UNIX, LAUNCHER_DIR_WIN

from .platform import Platform


class Launcher:

    def __init__(self, platform):

        self._platform = platform

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

            return LAUNCHER_DIR_WIN

        return LAUNCHER_DIR_UNIX

    def _script(self) -> str:

        entropy = APPLICATION_ROOT

        if self._platform == Platform.WINDOWS:

            return "@echo off\n" f'"{sys.executable}" ' f'"{entropy}" %*\n'

        return "#!/usr/bin/env bash\n\n" f'exec "{sys.executable}" ' f'"{entropy}" "$@"\n'
