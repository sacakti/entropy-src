"""
Offline wheel installer.
"""

import subprocess
import sys

from lib.install.paths import InstallerPathManager


class WheelInstaller:

    def __init__(self, platform):

        self._platform = platform

        self.paths = InstallerPathManager()

    def install(self):

        if not self.paths.requirements.exists():

            raise FileNotFoundError(f"Requirements file not found: {self.paths.requirements}")

        wheel_directory = self.paths.vendor / self._platform.value

        if not wheel_directory.exists():

            raise FileNotFoundError(f"Wheel directory not found: {wheel_directory}")

        self.paths.packages.mkdir(
            parents=True,
            exist_ok=True,
        )

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheel_directory),
            "--target",
            str(self.paths.packages),
            "-r",
            str(self.paths.requirements),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:

            print(result.stdout)
            print(result.stderr)

            raise RuntimeError("Failed to install Python packages.")
