#!/usr/bin/env python3
"""
Entropy bootstrap installer.

Usage:
    ./installer install entropy-1.1.1.epkg
    ./installer uninstall
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile, is_zipfile

APPLICATION_NAME = "Entropy"
PACKAGE_EXTENSION = ".epkg"

APPLICATION_ROOT = Path.home() / ".local" / "share" / "entropy"
APPLICATION_DIRECTORY = APPLICATION_ROOT / "application"

LAUNCHER_UNIX = Path.home() / ".local" / "bin" / "ent"
LAUNCHER_WINDOWS = Path.home() / "AppData" / "Local" / "Programs" / "Entropy" / "ent.cmd"


class InstallerError(RuntimeError):
    """Raised when bootstrap installation fails."""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install or uninstall Entropy.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    install = subparsers.add_parser(
        "install",
        help="Install Entropy from an .epkg package.",
    )
    install.add_argument(
        "package",
        type=Path,
        help="Entropy .epkg package.",
    )

    subparsers.add_parser(
        "uninstall",
        help="Uninstall Entropy.",
    )

    return parser.parse_args()


def validate_package(package: Path) -> None:
    """Validate the package structure before extraction."""

    if not package.exists():
        raise InstallerError(f"Package not found: {package}")

    if not package.is_file():
        raise InstallerError(f"Package is not a file: {package}")

    if package.suffix.lower() != PACKAGE_EXTENSION:
        raise InstallerError(
            "Package must use the '.epkg' extension.",
        )

    if not is_zipfile(package):
        raise InstallerError(f"Invalid Entropy package: {package}")

    try:
        with ZipFile(package, "r") as archive:
            names = set(archive.namelist())

            required_files = (
                "manifest.json",
                "application/entropy.py",
                "application/core/version.py",
            )

            required_directories = (
                "application/core/",
                "application/lib/",
                "application/resources/",
            )

            missing = [path for path in required_files if path not in names]

            missing.extend(
                directory
                for directory in required_directories
                if not any(name.startswith(directory) for name in names)
            )

            if missing:
                raise InstallerError(
                    "Package is missing required paths: " + ", ".join(missing),
                )

    except BadZipFile as exc:
        raise InstallerError(
            f"Invalid Entropy package: {package}",
        ) from exc


def read_manifest(package: Path) -> dict:
    """Read and validate basic package manifest metadata."""

    try:
        with ZipFile(package, "r") as archive:
            data = json.loads(
                archive.read("manifest.json").decode("utf-8"),
            )
    except (
        KeyError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        BadZipFile,
    ) as exc:
        raise InstallerError(
            "Package manifest is invalid.",
        ) from exc

    if not isinstance(data, dict):
        raise InstallerError(
            "Package manifest must be a JSON object.",
        )

    application = data.get("application")

    if not isinstance(application, dict):
        raise InstallerError(
            "Package manifest is missing application metadata.",
        )

    if application.get("name") != APPLICATION_NAME:
        raise InstallerError(
            "Package is not an Entropy application package.",
        )

    version = application.get("version")

    if not isinstance(version, str) or not version:
        raise InstallerError(
            "Package manifest contains an invalid application version.",
        )

    return data


def extract_application(
    package: Path,
    destination: Path,
) -> Path:
    """Extract the package and return its application directory."""

    try:
        with ZipFile(package, "r") as archive:
            archive.extractall(destination)
    except BadZipFile as exc:
        raise InstallerError(
            f"Invalid Entropy package: {package}",
        ) from exc

    application = destination / "application"

    if not application.is_dir():
        raise InstallerError(
            "Package does not contain an application directory.",
        )

    return application


def run_packaged_installer(
    application: Path,
) -> None:
    """Run the installer shipped with the packaged application."""

    installer = application / "lib" / "install" / "installer.py"

    if not installer.exists():
        raise InstallerError(
            "Package does not contain the Entropy installer.",
        )

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(application)

    process = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from lib.install.installer import Installer; "
                "import sys; "
                "result = Installer().install(); "
                "print(result.message); "
                "sys.exit(0 if result.success else 1)"
            ),
        ],
        cwd=application,
        env=environment,
        check=False,
    )

    if process.returncode != 0:
        raise InstallerError(
            "Entropy application installation failed.",
        )


def install(package: Path) -> None:
    """Install Entropy from an .epkg package."""

    package = package.expanduser().resolve()

    validate_package(package)
    manifest = read_manifest(package)
    version = manifest["application"]["version"]

    print(f"Installing {APPLICATION_NAME} {version}...")
    print()

    if APPLICATION_DIRECTORY.exists():
        raise InstallerError(
            "Entropy is already installed. " "Use 'ent upgrade --source <package>' to upgrade it.",
        )

    APPLICATION_ROOT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    staging = Path(
        tempfile.mkdtemp(
            prefix="entropy-install-",
            dir=str(APPLICATION_ROOT.parent),
        ),
    )

    try:
        application = extract_application(
            package,
            staging,
        )

        print("Package extracted.")
        print("Starting Entropy installation...")
        print()

        run_packaged_installer(application)

        print()
        print("Entropy installation completed.")

    finally:
        shutil.rmtree(
            staging,
            ignore_errors=True,
        )


def confirm_uninstall() -> bool:
    """Ask for explicit uninstall confirmation."""

    print()
    print("WARNING")
    print("-------")
    print("This operation will permanently remove Entropy.")
    print()
    print(f"Application: {APPLICATION_ROOT}")
    print(f"Data       : {Path.home() / '.entropy'}")
    print()
    print("The following will be removed:")
    print("  • Installed application")
    print("  • Database")
    print("  • Configuration")
    print("  • Installed Python packages")
    print("  • Plugins")
    print("  • Runtime files")
    print("  • Launcher")
    print()

    return input("Continue? [y/N]: ").strip().lower() in ("y", "yes")


def uninstall() -> None:
    """Remove the complete Entropy installation."""

    if not confirm_uninstall():
        print()
        print("Uninstallation cancelled.")
        return

    print()
    print("Uninstalling Entropy...")

    #
    # Remove application installation.
    #

    if APPLICATION_ROOT.exists():
        shutil.rmtree(
            APPLICATION_ROOT,
        )

    #
    # Remove persistent Entropy data.
    #

    entropy_home = Path.home() / ".entropy"

    if entropy_home.exists():
        shutil.rmtree(
            entropy_home,
        )

    #
    # Remove launcher.
    #

    launcher = LAUNCHER_WINDOWS if sys.platform.startswith("win") else LAUNCHER_UNIX

    if launcher.exists():
        launcher.unlink()

    print("Entropy uninstalled successfully.")


def main() -> int:
    args = parse_arguments()

    try:
        if args.command == "install":
            install(args.package)
        else:
            uninstall()

        return 0

    except KeyboardInterrupt:
        print("\nOperation cancelled.", file=sys.stderr)
        return 130

    except InstallerError as exc:
        print(f"Installer failed: {exc}", file=sys.stderr)
        return 1

    except Exception as exc:
        print(f"Installer failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
