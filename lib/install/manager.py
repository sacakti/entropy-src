"""
Installation manager.
"""

from .installer import Installer
from .uninstaller import Uninstaller


class InstallManager:

    def __init__(self):

        self._installer = Installer()

        self._uninstaller = Uninstaller()

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def install(self):

        return self._installer.install()

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def uninstall(self):

        return self._uninstaller.uninstall()