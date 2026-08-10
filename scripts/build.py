#!/usr/bin/env python3

"""
Entropy application package builder.

Builds an Entropy .epkg release package from the
current source tree.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from packaging.version import InvalidVersion, Version

APPLICATION_NAME = "Entropy"
PACKAGE_FORMAT = 1
PACKAGE_TYPE = "application"
PACKAGE_EXTENSION = ".epkg"
BUILD_PATH = "build"

MINIMUM_PYTHON = "3.9"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

APPLICATION_VERSION_FILE = PROJECT_ROOT / "core" / "version.py"

REQUIRED_PATHS = ("entropy.py", "core", "lib", "resources")

EXCLUDED_NAMES = {
    ".DS_Store",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
}


class BuildError(RuntimeError):
    """
    Raised when an Entropy package cannot be built.
    """


def main() -> int:

    args = parse_arguments()

    try:

        version = validate_version(
            args.version,
        )

        validate_source_tree()

        output = build_package(
            version,
            args.output,
        )

        verify_package(
            output,
            version,
        )

        print()
        print("Entropy package built successfully.")
        print()
        print(f"Version : {version}")
        print(f"Package : {output}")
        print()

        return 0

    except BuildError as exc:

        print(
            f"Build failed: {exc}",
            file=sys.stderr,
        )

        return 1


# ------------------------------------------------------------------
# Arguments
# ------------------------------------------------------------------


def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="Build an Entropy .epkg application package.",
    )

    parser.add_argument(
        "version",
        help="Release version, for example 2.0.0.",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=("Output .epkg path. " "Defaults to entropy.<version>.epkg."),
    )

    return parser.parse_args()


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------


def validate_version(
    value: str,
) -> str:
    """
    Validate the release version.
    """

    try:

        version = Version(
            value,
        )

    except InvalidVersion as exc:

        raise BuildError(
            f"Invalid release version: {value}",
        ) from exc

    if version != Version(str(version)):

        raise BuildError(
            f"Invalid normalized release version: {value}",
        )

    return str(version)


def validate_source_tree() -> None:
    """
    Validate the source tree before packaging.
    """

    if not PROJECT_ROOT.exists():

        raise BuildError(
            f"Project root does not exist: {PROJECT_ROOT}",
        )

    for relative in REQUIRED_PATHS:

        path = PROJECT_ROOT / relative

        if not path.exists():

            raise BuildError(
                f"Required source path is missing: {relative}",
            )

    if not APPLICATION_VERSION_FILE.exists():

        raise BuildError(
            "Application version file is missing: " f"{APPLICATION_VERSION_FILE}",
        )


# ------------------------------------------------------------------
# Build
# ------------------------------------------------------------------


def build_package(
    version: str,
    output: Path | None,
) -> Path:
    """
    Build an Entropy .epkg package.
    """

    if output is None:

        output = PROJECT_ROOT / BUILD_PATH / f"entropy.{version}.epkg"

    output = output.expanduser().resolve()

    if output.suffix.lower() != PACKAGE_EXTENSION:

        raise BuildError(
            "Output package must use the '.epkg' extension.",
        )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output.exists():

        output.unlink()

    with tempfile.TemporaryDirectory(
        prefix="entropy-build-",
    ) as temporary:

        root = Path(
            temporary,
        )

        application = root / "application"

        application.mkdir()

        #
        # Copy application source.
        #

        copy_application(
            application,
        )

        #
        # Generate runtime version.
        #

        write_version_file(
            application,
            version,
        )

        #
        # Generate manifest.
        #

        manifest = create_manifest(
            version,
        )

        write_manifest(
            root,
            manifest,
        )

        #
        # Create package.
        #

        create_archive(
            root,
            output,
        )

    return output


# ------------------------------------------------------------------
# Application
# ------------------------------------------------------------------


def copy_application(
    destination: Path,
) -> None:
    """
    Copy only the runtime application into the package.
    """

    sources = (
        PROJECT_ROOT / "entropy.py",
        PROJECT_ROOT / "core",
        PROJECT_ROOT / "lib",
        PROJECT_ROOT / "resources",
    )

    for source in sources:

        if not source.exists():

            raise BuildError(
                f"Required application source is missing: {source}",
            )

        target = destination / source.name

        if source.is_dir():

            shutil.copytree(
                source,
                target,
                ignore=shutil.ignore_patterns(
                    ".DS_Store",
                    "__pycache__",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                ),
            )

        else:

            shutil.copy2(
                source,
                target,
            )


def write_version_file(
    application: Path,
    version: str,
) -> None:
    """
    Generate the runtime version file.
    """

    version_file = application / "core" / "version.py"

    version_file.write_text(
        f'''"""
Entropy application version.
"""

APP_NAME = "{APPLICATION_NAME}"
VERSION = "{version}"
''',
        encoding="utf-8",
    )


# ------------------------------------------------------------------
# Manifest
# ------------------------------------------------------------------


def create_manifest(
    version: str,
) -> dict:
    """
    Create the package manifest.
    """

    return {
        "format": PACKAGE_FORMAT,
        "application": {
            "name": APPLICATION_NAME,
            "version": version,
            "minimum_python": MINIMUM_PYTHON,
        },
        "package": {
            "type": PACKAGE_TYPE,
            "format": "epkg",
        },
    }


def write_manifest(
    root: Path,
    manifest: dict,
) -> None:
    """
    Write manifest.json.
    """

    path = root / "manifest.json"

    path.write_text(
        json.dumps(
            manifest,
            indent=4,
        )
        + "\n",
        encoding="utf-8",
    )


# ------------------------------------------------------------------
# Archive
# ------------------------------------------------------------------


def create_archive(
    root: Path,
    output: Path,
) -> None:
    """
    Create the .epkg ZIP archive.
    """

    with ZipFile(
        output,
        "w",
        compression=ZIP_DEFLATED,
    ) as archive:

        for path in sorted(
            root.rglob("*"),
        ):

            if not path.is_file():
                continue

            relative = path.relative_to(
                root,
            )

            archive.write(
                path,
                relative.as_posix(),
            )


# ------------------------------------------------------------------
# Verification
# ------------------------------------------------------------------


def verify_package(
    package: Path,
    version: str,
) -> None:
    """
    Verify the generated package.
    """

    if not package.exists():

        raise BuildError(
            f"Package was not created: {package}",
        )

    try:

        with ZipFile(
            package,
            "r",
        ) as archive:

            names = set(
                archive.namelist(),
            )

            required_files = (
                "manifest.json",
                "application/entropy.py",
                "application/core/version.py",
            )

            required_directories = (
                "application/core/",
                "application/lib/",
            )

            missing_files = [path for path in required_files if path not in names]

            missing_directories = [
                directory
                for directory in required_directories
                if not any(name.startswith(directory) for name in names)
            ]

            missing = [
                *missing_files,
                *missing_directories,
            ]

            if missing:

                raise BuildError(
                    "Generated package is missing required " f"paths: {', '.join(missing)}",
                )

            manifest = json.loads(
                archive.read(
                    "manifest.json",
                ).decode("utf-8"),
            )

            package_version = manifest["application"]["version"]

            if package_version != version:

                raise BuildError(
                    "Manifest version does not match "
                    f"requested version: "
                    f"{package_version} != {version}",
                )

            version_source = archive.read(
                "application/core/version.py",
            ).decode("utf-8")

            expected = f'VERSION = "{version}"'

            if expected not in version_source:

                raise BuildError(
                    "Runtime application version does not " "match package version.",
                )

    except BuildError:
        raise

    except Exception as exc:

        raise BuildError(
            f"Unable to verify generated package: {exc}",
        ) from exc


if __name__ == "__main__":

    raise SystemExit(
        main(),
    )
