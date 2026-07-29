#!/usr/bin/env python3

"""
Download offline wheels for Entropy.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

VENDOR_DIR = PROJECT_ROOT / "core" / "vendor"
REQUIREMENTS = VENDOR_DIR / "requirements.txt"

SUPPORTED_PLATFORMS = {
    "linux": "manylinux2014_x86_64",
    # "mac": "macosx_11_0_x86_64",
    "windows": "win_amd64",
}


def parse_arguments():

    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--all",
        action="store_true",
        help="Download wheels for all supported platforms.",
    )

    group.add_argument(
        "--platform",
        choices=["linux", "mac", "windows"],
        help=(
            "Target platform. "
            "Use 'python download_wheels.py --machine' "
            "to determine the native platform."
        ),
    )

    parser.add_argument(
        "--python",
        default="3.9",
        help="Python version (default: 3.9).",
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing wheels before downloading.",
    )

    parser.add_argument(
        "--info",
        action="store_true",
        help="Display the current operating system and CPU architecture.",
    )

    return parser.parse_args()

def current_machine():

    return platform.machine().lower()

def mac_platform():

    machine = current_machine()

    if machine in ("arm64", "aarch64"):
        return "macosx_11_0_arm64"

    if machine == "x86_64":
        return "macosx_10_9_x86_64"

    raise RuntimeError(
        f"Unsupported macOS architecture: {machine}"
    )

def current_platform():

    mapping = {
        "Linux": "linux",
        "Darwin": "mac",
        "Windows": "windows",
    }

    system = platform.system()

    try:
        return mapping[system]
    except KeyError as err:
        raise RuntimeError(
            f"Unsupported platform: {system}"
        ) from err


def download(platform_name, python_version, clean):

    target = VENDOR_DIR / platform_name

    if clean and target.exists():

        shutil.rmtree(target)

    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    version = python_version.replace(".", "")

    # command = [
    #     sys.executable,
    #     "-m",
    #     "pip",
    #     "download",
    #     "--only-binary=:all:",
    #     "--dest",
    #     str(target),
    #     "--platform",
    #     SUPPORTED_PLATFORMS[platform_name],
    #     "--implementation",
    #     "cp",
    #     "--python-version",
    #     version,
    #     "--abi",
    #     f"cp{version}",
    #     "-r",
    #     str(REQUIREMENTS),
    # ]

    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--only-binary=:all:",
        "--dest",
        str(target),
    ]

    if platform_name == "mac":

        command.extend([
            "--platform",
            mac_platform(),
        ])

    else:

        command.extend([
            "--platform",
            SUPPORTED_PLATFORMS[platform_name],
        ])

    command.extend([
        "--implementation",
        "cp",
        "--python-version",
        version,
        "--abi",
        f"cp{version}",
        "-r",
        str(REQUIREMENTS),
    ])

    print(f"\nDownloading {platform_name} wheels...")

    subprocess.run(
        command,
        check=True,
    )


def main():

    args = parse_arguments()

    if args.info:

        print(f"Operating System : {platform.system()}")
        print(f"Architecture     : {platform.machine()}")
        # print(f"Platform Tag     : {SUPPORTED_PLATFORMS}")
        return

    if args.all:

        platforms = SUPPORTED_PLATFORMS.keys()

    elif args.platform:

        platforms = [args.platform]

    else:

        platforms = [current_platform()]

    for platform_name in platforms:

        download(
            platform_name,
            args.python,
            args.clean,
        )

    print("\nDone.")


if __name__ == "__main__":

    main()
