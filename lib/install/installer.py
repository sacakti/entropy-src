
"""
Entropy installer.
"""

import os
import shutil
from dataclasses import dataclass

from core.constants import CONFIG_DIR, CONFIG_FILE, DATABASE_DIR, DEFAULT_CONFIG_FILE, ENTROPY_HOME

from .launcher import Launcher
from .platform import PlatformDetector
from .wheels import WheelInstaller


@dataclass
class InstallerResult:

    success: bool

    message: str

success_msg = f"""
==================================================
Entropy installed successfully.
==================================================

Installation Directory
    {ENTROPY_HOME}

Configuration
    {CONFIG_FILE}

Launcher
    ~/.local/bin/ent

"""

class Installer:

    def install(self) -> InstallerResult:

        try:

            platform = PlatformDetector.detect()

            #
            # Install Python dependencies
            #

            WheelInstaller(
                platform,
            ).install()

            #
            # Create Entropy home
            #

            self._create_directories()

            #
            # Create config
            #

            self._create_config()

            #
            # Install launcher
            #
            launcher = self._install_launcher(platform)

            if not launcher.exists():
                raise RuntimeError("Failed to create launcher.")

            #
            # Verify PATH
            #
            path_resp = self._verify_path(launcher)

            message = success_msg + path_resp

            return InstallerResult(
                success=True,
                message=message,
            )

        except Exception as exc:

            return InstallerResult(
                success=False,
                message=str(exc),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_directories(self):

        for directory in (
            ENTROPY_HOME,
            CONFIG_DIR,
            DATABASE_DIR,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _create_config(self):

        if not CONFIG_FILE.exists():

            shutil.copy2(DEFAULT_CONFIG_FILE, CONFIG_FILE)

    def _install_launcher(self, platform):
        return Launcher(
            platform,
        ).install()

    def _verify_path(self, launcher):

        launcher_dir = str(launcher.parent)

        paths = os.environ.get("PATH", "").split(os.pathsep)

        shell = os.environ.get("SHELL", "")

        reload_cmd = "Restart your shell"

        if shell.endswith("zsh"):
            reload_cmd = "source ~/.zshrc"
        elif shell.endswith("bash"):
            reload_cmd = "source ~/.bashrc"

        path_exists = launcher_dir in paths

        launcher_not_exists = f'''
The launcher directory is not on your PATH.

Add the following line to your shell profile (~/.zshrc, ~/.bashrc, etc.):

    export PATH="$HOME/.local/bin:$PATH"

Then reload your shell:

    {reload_cmd}

or open a new terminal.

After that, run:

    ent
'''
        if path_exists:
            return """
You can now start Entropy by running:

    ent
"""
        else:
            return launcher_not_exists
