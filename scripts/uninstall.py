#!/usr/bin/env python3


from lib.install.manager import InstallManager
from lib.install.paths import InstallerPathManager

def confirm() -> bool:
    paths = InstallerPathManager()
    print()
    print("WARNING")
    print("-------")
    print("This operation will permanently remove Entropy.")
    print()
    print(f"Location: {paths.home}")
    print()
    print("The following data will be deleted:")
    print("  • Database")
    print("  • Configuration")
    print("  • Installed Python packages")
    print("  • Runtime files")
    print()

    response = input("Continue? [y/N]: ").strip().lower()

    return response in ("y", "yes")


def main():

    if not confirm():

        print("\nUninstallation cancelled.")

        return

    result = InstallManager().uninstall()

    print(result.message)


if __name__ == "__main__":

    main()
