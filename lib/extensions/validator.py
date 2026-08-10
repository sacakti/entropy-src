"""
Extension validator.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from core.context import EntropyContext
from lib.database.repositories.extensions import ExtensionRepository
from lib.extensions.exceptions import ExtensionInstallationError


class ExtensionValidator:
    """
    Validates extension availability.
    """

    def __init__(
        self,
        context: EntropyContext,
        repository: ExtensionRepository,
    ) -> None:

        assert context.paths is not None

        self._paths = context.paths.extensions

        self._repository = repository

    #
    # Helper
    #

    def _installed_files(
        self,
        record: Path,
    ) -> list[Path]:
        """
        Return files recorded by RECORD.
        """

        warnings.warn(
            "_installed_files() is deprecated.",
            DeprecationWarning,
            stacklevel=2,
        )

        import csv

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
    # Installed
    # ------------------------------------------------------------------

    def exists(
        self,
        name: str,
    ) -> bool:
        """
        Return True if an extension is installed.
        """

        return self._repository.exists(
            name,
        )

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------

    def version(
        self,
        name: str,
    ) -> str | None:
        """
        Return the installed version.
        """

        return self._repository.version(
            name,
        )

    # ------------------------------------------------------------------
    # Wheel
    # ------------------------------------------------------------------

    def wheel(
        self,
        name: str,
    ) -> Path | None:
        """
        Return the latest available wheel for an extension.
        """

        wheels = sorted(
            self._paths.wheels.glob(
                f"{name}-*.whl",
            )
        )

        if not wheels:

            return None

        return wheels[-1]

    # Wheels
    def wheels(
        self,
    ) -> list[Path]:
        """
        Return locally available extension wheels.
        """

        return sorted(
            self._paths.wheels.glob(
                "*.whl",
            ),
            key=lambda path: path.name.lower(),
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------
    def verify(
        self,
        name: str,
    ) -> None:
        """
        Verify an installed extension.

        Verifies that the extension is registered in the database,
        that its dist-info directory exists, that RECORD exists,
        and that all files listed by RECORD are present.
        """

        warnings.warn(
            "verify() is deprecated.",
            DeprecationWarning,
            stacklevel=2,
        )

        extension = self._repository.get_by_name(
            name,
        )

        dist_info = self._paths.site_packages / extension.dist_info

        if not dist_info.exists():

            raise ExtensionInstallationError(
                f"Dist-info directory not found for '{name}': " f"{dist_info}",
            )

        record = dist_info / "RECORD"

        if not record.exists():

            raise ExtensionInstallationError(
                f"RECORD not found for '{name}'.",
            )

        missing: list[Path] = []

        for target in self._installed_files(
            record,
        ):

            if not target.exists():

                missing.append(
                    target,
                )

        if missing:

            files = "\n".join(f"  - {path}" for path in missing)

            raise ExtensionInstallationError(
                f"Extension '{name}' is incomplete. "
                f"Missing {len(missing)} installed file(s):\n"
                f"{files}",
            )

        for entry_point in extension.entry_points:

            launcher = self._paths.site_packages / "bin" / entry_point

            if not launcher.exists():

                raise ExtensionInstallationError(
                    f"Entry point launcher not found for " f"'{name}': {launcher}",
                )
