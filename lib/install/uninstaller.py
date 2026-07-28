"""
Entropy uninstaller.
"""

import shutil

from core.constants import ENTROPY_HOME

from .launcher import Launcher
from .platform import PlatformDetector
from .installer import InstallerResult


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
    
        if ENTROPY_HOME.exists():

            shutil.rmtree(
                ENTROPY_HOME
            )