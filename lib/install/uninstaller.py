"""
Entropy uninstaller.
"""

import shutil

from lib.install.paths import InstallerPathManager

from .installer import InstallerResult
from .launcher import Launcher
from .platform import PlatformDetector


class Uninstaller:

    def __init__(self) -> None:

        self._paths = InstallerPathManager()

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def uninstall(self) -> InstallerResult:

        try:

            platform = PlatformDetector.detect()

            Launcher(
                platform,
                self._paths,
            ).uninstall()

            # self._remove_home()
            self._remove_installation()

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

    def _remove_installation(self) -> None:
        """
        Remove Entropy persistent data and installed application.
        """

        if self._paths.home.exists():

            shutil.rmtree(
                self._paths.home,
            )

        if self._paths.application_root.exists():

            shutil.rmtree(
                self._paths.application_root,
            )
