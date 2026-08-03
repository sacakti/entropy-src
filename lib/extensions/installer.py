"""
Offline extension installer.
"""
from __future__ import annotations
from pathlib import Path
import sys
import csv
from configparser import ConfigParser

from core.context import EntropyContext

from lib.extensions.base import BaseInstaller
from lib.extensions.exceptions import ExtensionInstallationError
from lib.models.extensions import Extension, ExtensionManifest
from lib.extensions.inspector import WheelInspector

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

            package = (
                f"{package}=={manifest.version}"
            )

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

        for entry_point in extension.entry_points:

            launcher = (
                self._paths.site_packages /
                "bin" /
                entry_point
            )

            if launcher.exists():

                self._executor.remove(
                    launcher,
                )

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

            try:

                directory.rmdir()

            except OSError:

                #
                # Directory is not empty.
                #

                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _find_dist_info(
        self,
        extension: Extension,
    ) -> str:
        """
        Locate the installed dist-info directory.
        """

        matches = list(
            self._paths.site_packages.glob(
                f"{extension.name.replace('-', '_')}-*.dist-info",
            )
        )

        if len(matches) != 1:

            raise ExtensionInstallationError(
                f"Unable to determine dist-info for '{extension.name}'.",
            )

        return matches[0].name

    def _record_file(
        self,
        extension: Extension,
    ) -> Path:
        """
        Return the RECORD file.
        """

        record = (
            self._paths.site_packages /
            extension.dist_info /
            "RECORD"
        )

        if not record.exists():

            raise ExtensionInstallationError(
                f"RECORD not found for '{extension.name}'."
            )

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
                    self._paths.site_packages /
                    row[0],
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

        file = (
            self._paths.site_packages /
            extension.dist_info /
            "entry_points.txt"
        )

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
