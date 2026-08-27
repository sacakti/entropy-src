"""
Offline extension installer.
"""

from __future__ import annotations

import csv
import sys
from configparser import ConfigParser
from contextlib import suppress
from pathlib import Path
from email.parser import Parser

from core.context import EntropyContext
from lib.extensions.base import BaseInstaller
from lib.extensions.exceptions import ExtensionInstallationError
from lib.extensions.inspector import WheelInspector
from lib.models.extensions import Extension, ExtensionManifest


class OfflineInstaller(BaseInstaller):
    """
    Installs extensions from the local wheel repository.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.executor is not None
        assert context.paths is not None

        self._executor = context.executor
        self._paths = context.paths.extensions
        self._inspector = WheelInspector()

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def _build_install_command(
        self,
        manifest: ExtensionManifest,
    ) -> list[str]:
        """
        Build the pip install command.
        """

        package = manifest.name

        if manifest.version:

            package = f"{package}=={manifest.version}"

        return [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-index",
            "--find-links",
            str(
                self._paths.wheels,
            ),
            "--target",
            str(
                self._paths.site_packages,
            ),
            package,
        ]

    def _execute_install(
        self,
        manifest: ExtensionManifest,
    ) -> None:
        """
        Execute pip installation.
        """

        command = self._build_install_command(
            manifest,
        )

        result = self._executor.run(
            command,
        )

        if result.exit_code != 0:

            raise ExtensionInstallationError(
                result.stderr or result.stdout,
            )

    def install(
        self,
        manifest: ExtensionManifest,
        wheel: Path,
    ) -> Extension:
        """
        Install an extension from the local wheel repository.
        """

        self._execute_install(
            manifest,
        )

        extension = self._inspector.inspect(
            wheel,
        )

        extension.dist_info = self._find_dist_info(
            extension,
        )

        extension.entry_points = self._find_entry_points(
            extension,
        )

        return extension

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def uninstall(
        self,
        extension: Extension,
    ) -> None:
        """
        Uninstall an extension.
        """

        record = self._record_file(
            extension,
        )

        for target in self._installed_files(
            record,
        ):

            if target.exists():

                self._executor.remove(
                    target,
                )

        self._executor.remove(
            record.parent,
        )

        self._cleanup(
            self._paths.site_packages,
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(
        self,
        extension: Extension,
    ) -> None:
        """
        Verify an installed extension.

        Verifies the dist-info directory, RECORD file, and
        every file recorded by RECORD.
        """

        dist_info = self._paths.site_packages / extension.dist_info

        if not dist_info.exists():

            raise ExtensionInstallationError(
                f"Dist-info directory not found for " f"'{extension.name}': {dist_info}",
            )

        if not dist_info.is_dir():

            raise ExtensionInstallationError(
                f"Dist-info path is not a directory for " f"'{extension.name}': {dist_info}",
            )

        record = dist_info / "RECORD"

        if not record.exists():

            raise ExtensionInstallationError(
                f"RECORD not found for '{extension.name}'.",
            )

        if not record.is_file():

            raise ExtensionInstallationError(
                f"RECORD path is not a file for " f"'{extension.name}': {record}",
            )

        missing = [
            path
            for path in self._installed_files(
                record,
            )
            if not path.exists()
        ]

        if missing:

            files = "\n".join(f"- {path}" for path in missing)

            raise ExtensionInstallationError(
                f"Extension '{extension.name}' is incomplete. "
                f"Missing {len(missing)} installed file(s):\n\n"
                f"{files}",
            )

    #
    # Repair
    #
    def repair(
        self,
        extension: Extension,
        wheel: Path,
    ) -> Extension:
        """
        Repair an extension installation from its local wheel.
        """

        if not wheel.exists():

            raise ExtensionInstallationError(
                f"Wheel not found for '{extension.name}': {wheel}",
            )

        self.uninstall(
            extension,
        )

        manifest = ExtensionManifest(
            name=extension.name,
            version=extension.version,
            installer=extension.installer,
        )

        return self.install(
            manifest,
            wheel,
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(
        self,
        root: Path,
    ) -> None:
        """
        Remove empty directories.
        """

        for directory in sorted(
            root.rglob("*"),
            key=lambda path: len(path.parts),
            reverse=True,
        ):

            if not directory.is_dir():
                continue

            with suppress(OSError):

                directory.rmdir()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _find_dist_info(
        self,
        extension: Extension,
    ) -> str:
        """
        Locate the installed dist-info directory.

        The distribution name in a wheel filename and the actual
        dist-info directory name may differ in normalization and case.
        Therefore, inspect the installed METADATA instead of deriving
        the directory name from the extension name.
        """

        from packaging.utils import canonicalize_name

        expected_name = canonicalize_name(
            extension.name,
        )

        matches: list[Path] = []

        for directory in self._paths.site_packages.glob(
            "*.dist-info",
        ):

            metadata = directory / "METADATA"

            if not metadata.is_file():
                continue

            try:

                content = metadata.read_text(
                    encoding="utf-8",
                )

                message = Parser().parsestr(
                    content,
                )

            except (OSError, UnicodeDecodeError):

                continue

            name = message.get(
                "Name",
            )

            version = message.get(
                "Version",
            )

            if name is None or version is None:
                continue

            if canonicalize_name(name) != expected_name:
                continue

            if version != extension.version:
                continue

            matches.append(
                directory,
            )

        if len(matches) == 1:

            return matches[0].name

        if not matches:

            raise ExtensionInstallationError(
                f"Unable to determine dist-info for "
                f"'{extension.name}=={extension.version}'.",
            )

        directories = ", ".join(
            directory.name
            for directory in matches
        )

        raise ExtensionInstallationError(
            f"Multiple dist-info directories found for "
            f"'{extension.name}=={extension.version}': {directories}",
        )

    def _record_file(
        self,
        extension: Extension,
    ) -> Path:
        """
        Return the RECORD file.
        """

        record = self._paths.site_packages / extension.dist_info / "RECORD"

        if not record.exists():

            raise ExtensionInstallationError(f"RECORD not found for '{extension.name}'.")

        return record

    def _installed_files(
        self,
        record: Path,
    ) -> list[Path]:
        """
        Return all installed files.
        """

        files: list[Path] = []

        with record.open(
            newline="",
            encoding="utf-8",
        ) as stream:

            reader = csv.reader(
                stream,
            )

            for row in reader:

                if not row:
                    continue

                files.append(
                    self._paths.site_packages / row[0],
                )

        return files

    # ------------------------------------------------------------------
    # Entry Points
    # ------------------------------------------------------------------

    def _find_entry_points(
        self,
        extension: Extension,
    ) -> list[str]:
        """
        Return installed console entry points.
        """

        file = self._paths.site_packages / extension.dist_info / "entry_points.txt"

        if not file.exists():

            return []

        parser = ConfigParser()

        parser.read(
            file,
            encoding="utf-8",
        )

        if not parser.has_section(
            "console_scripts",
        ):

            return []

        return sorted(
            parser.options(
                "console_scripts",
            )
        )
