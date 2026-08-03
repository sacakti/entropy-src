"""
Entropy installer.
"""

import os
import shutil
import sys
import traceback
from dataclasses import dataclass

from lib.install.console import InstallerConsole
from lib.install.paths import InstallerPathManager
from lib.install.directory import DirectoryInstaller

from .launcher import Launcher
from .platform import PlatformDetector
from .wheels import WheelInstaller

paths = InstallerPathManager()
console = InstallerConsole()

@dataclass
class InstallerResult:

    success: bool

    message: str


success_msg = f"""
==================================================
Entropy installed successfully.
==================================================

Installation Directory
    {paths.home}

Configuration
    {paths.entropy_config}

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

            console.step("Installing Python packages...")

            WheelInstaller(
                platform,
            ).install()

            console.success("Python packages installed.")

            #
            # Create Entropy home
            #

            console.step("Creating directories...")

            DirectoryInstaller().install()

            console.success("Directories created.")

            #
            # Create configuration
            #

            console.step("Installing configuration...")

            self._create_config()

            console.success("Configuration installed.")

            #
            # Build installation context
            #

            sys.path.insert(
                0,
                str(paths.packages),
            )

            from core.context_factory import ContextFactory
            from lib.install.bootstrap import BootstrapInstaller
            from lib.install.database import DatabaseInstaller

            factory = ContextFactory(
                project_root=paths.project_root,
                entropy_home=paths.staging,
            )

            factory.bootstrap()

            factory.runtime()

            factory.infrastructure()

            #
            # Install database
            #

            console.step("Installing database...")

            DatabaseInstaller(
                factory.context,
            ).install()

            console.success("Database installed.")

            #
            # Create administrator
            #

            console.step("Creating bootstrap administrator...")

            factory.services()

            BootstrapInstaller(
                factory.context,
            ).install()

            console.success("Bootstrap administrator created.")

            paths.commit()

            #
            # Install launcher
            #

            console.step("Installing launcher...")

            launcher = self._install_launcher(
                platform,
            )

            if not launcher.exists():

                raise RuntimeError(
                    "Failed to create launcher.",
                )

            console.success("Launcher installed.")

            #
            # Verify PATH
            #

            console.step("Verifying PATH...")

            path_response = self._verify_path(
                launcher,
            )

            console.success("Installation completed.")

            message = success_msg + path_response

            return InstallerResult(
                success=True,
                message=message,
            )

        except Exception:

            paths.rollback()

            traceback.print_exc()

            return InstallerResult(
                success=False,
                message="Installation failed.",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------


    def _create_config(self):

        # Entropy config

        if not paths.config_file.exists():

            shutil.copy2(paths.default_config, paths.config_file)

        # Default workflow json

        if not paths.config_file.exists():

            shutil.copy2(paths.default_workflow, paths.workflow_file)

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

        launcher_not_exists = f"""
The launcher directory is not on your PATH.

Add the following line to your shell profile (~/.zshrc, ~/.bashrc, etc.):

    export PATH="$HOME/.local/bin:$PATH"

Then reload your shell:

    {reload_cmd}

or open a new terminal.

After that, run:

    ent
"""
        if path_exists:
            return """
You can now start Entropy by running:

    ent
"""
        else:
            return launcher_not_exists
