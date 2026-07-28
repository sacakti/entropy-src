"""
Offline wheel installer.
"""

from pathlib import Path
import subprocess
from core.constants import PACKAGE_DIR, VENDOR_DIR, REQUIREMENT_FILE
import sys

class WheelInstaller:

    def __init__(self, platform):

        self._platform = platform

    def install(
        self
    ):

        if not REQUIREMENT_FILE.exists():

            raise FileNotFoundError(
                f"Requirements file not found: {REQUIREMENT_FILE}"
            )

        wheel_directory = (
            VENDOR_DIR /
            self._platform.value
        )

        if not wheel_directory.exists():

            raise FileNotFoundError(
                f"Wheel directory not found: {wheel_directory}"
            )
        
        PACKAGE_DIR.mkdir(
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
            str(PACKAGE_DIR),
            "-r",
            str(REQUIREMENT_FILE),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:

            print(result.stdout)
            print(result.stderr)

            raise RuntimeError(
                "Failed to install Python packages."
            )

        # print(f"Python Packages installed sucessfully.")