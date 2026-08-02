"""
Entropy uninstaller.
"""

import shutil

from lib.install.paths import InstallerPathManager

from .installer import InstallerResult
from .launcher import Launcher
from .platform import PlatformDetector


class Uninstaller:

    def uninstall(self) -> InstallerResult:

        try:

            platform = PlatformDetector.detect()

            Launcher(platform).uninstall()

            self._remove_home()

            return InstallerResult(
                success=True,
                message="Entropy uninstalled successfully.",
            )

        except Exception as exc:

            return InstallerResult(
                success=False,
                message=str(exc),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _remove_home(self):

        self.paths = InstallerPathManager()

        if self.paths.home.exists():

            shutil.rmtree(self.paths.home)
