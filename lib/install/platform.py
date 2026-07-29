"""
Platform detection.
"""

import platform
from enum import Enum


class Platform(Enum):

    LINUX = "linux"

    MAC = "mac"

    WINDOWS = "windows"


class PlatformDetector:

    @staticmethod
    def detect() -> Platform:

        system = platform.system()

        if system == "Linux":
            return Platform.LINUX

        if system == "Darwin":
            return Platform.MAC

        if system == "Windows":
            return Platform.WINDOWS

        raise RuntimeError(f"Unsupported platform: {system}")
