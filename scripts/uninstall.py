#!/usr/bin/env python3

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)

from lib.install.manager import InstallManager
from lib.install.paths import InstallerPathManager


def confirm() -> bool:
    paths = InstallerPathManager()

    print()
    print("WARNING")
    print("-------")
    print("This operation will permanently remove Entropy.")
    print()
    print(f"Entropy Data: {paths.home}")
    print("Installed application: " f"{paths.application_root}")
    print()

    print("The following data will be deleted:")
    print("  • Installed application")
    print("  • Application versions and backups")
    print("  • Database")
    print("  • Configuration")
    print("  • Installed Python packages")
    print("  • Plugins")
    print("  • Runtime files")
    print()

    response = (
        input(
            "Continue? [y/N]: ",
        )
        .strip()
        .lower()
    )

    return response in ("y", "yes")


def main() -> int:

    if not confirm():

        print(
            "\nUninstallation cancelled.",
        )

        return 0

    result = InstallManager().uninstall()

    print(
        result.message,
    )

    return 0 if result.success else 1


if __name__ == "__main__":

    raise SystemExit(
        main(),
    )
