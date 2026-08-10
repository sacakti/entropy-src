"""
Offline wheel installer.
"""

import subprocess
import sys

from lib.install.paths import InstallerPathManager


class WheelInstaller:

    def __init__(
        self,
        platform,
        paths: InstallerPathManager,
    ) -> None:

        self._platform = platform
        self._paths = paths

    def install(self):

        print(f"Wheel install method")

        if not self._paths.requirements.exists():

            raise FileNotFoundError(f"Requirements file not found: {self._paths.requirements}")

        wheel_directory = self._paths.vendor / self._platform.value

        if not wheel_directory.exists():

            raise FileNotFoundError(f"Wheel directory not found: {wheel_directory}")

        self._paths.packages.mkdir(
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
            str(self._paths.packages),
            "-r",
            str(self._paths.requirements),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        print("Python executable:", sys.executable)
        print("Package target:", self._paths.packages)
        print(
            "packaging directory:",
            self._paths.packages / "packaging",
            "exists=",
            (self._paths.packages / "packaging").exists(),
        )
        print(
            "packaging dist-info:",
            list(self._paths.packages.glob("packaging-*.dist-info")),
        )
        print(result.stdout)
        print(result.stderr)

        if result.returncode != 0:

            print(result.stdout)
            print(result.stderr)

            raise RuntimeError("Failed to install Python packages.")
