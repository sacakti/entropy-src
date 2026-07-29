#!/usr/bin/env python3

from ..core.constants import ENTROPY_HOME
from ..lib.install.manager import InstallManager


def confirm() -> bool:

    print()
    print("WARNING")
    print("-------")
    print("This operation will permanently remove Entropy.")
    print()
    print(f"Location: {ENTROPY_HOME}")
    print()
    print("The following data will be deleted:")
    print("  • Database")
    print("  • Configuration")
    print("  • Installed Python packages")
    print("  • Runtime files")
    print()

    response = input(
        "Continue? [y/N]: "
    ).strip().lower()

    return response in ("y", "yes")


def main():

    if not confirm():

        print("\nUninstallation cancelled.")

        return

    result = (
        InstallManager()
        .uninstall()
    )

    print(result.message)


if __name__ == "__main__":

    main()
