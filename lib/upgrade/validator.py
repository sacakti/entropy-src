"""
Upgrade package validator.
"""

from __future__ import annotations

import sys

from packaging.version import InvalidVersion, Version

from .exceptions import (
    DowngradeNotAllowedError,
    UpgradeManifestError,
    UpgradeNotRequiredError,
    UpgradePackageFormatError,
    UpgradeVersionError,
)
from .manifest import PackageManifest
from .package import UpgradePackage


class UpgradeValidator:
    """
    Validates an Entropy upgrade package.
    """

    EXPECTED_FORMAT = 1
    EXPECTED_PACKAGE_TYPE = "application"
    EXPECTED_APPLICATION = "Entropy"

    def validate(
        self,
        package: UpgradePackage,
        current_version: str,
    ) -> PackageManifest:
        """
        Validate an upgrade package against the
        currently installed application.
        """

        manifest = package.manifest()

        self._validate_format(
            manifest,
        )

        self._validate_application(
            manifest,
        )

        self._validate_python(
            manifest,
        )

        self._validate_version(
            current_version,
            manifest.application.version,
        )

        self._validate_application_files(
            package,
        )

        return manifest

    # ------------------------------------------------------------------
    # Format
    # ------------------------------------------------------------------

    def _validate_format(
        self,
        manifest: PackageManifest,
    ) -> None:

        if manifest.format != self.EXPECTED_FORMAT:

            raise UpgradePackageFormatError(
                f"Unsupported Entropy package format: "
                f"{manifest.format}. "
                f"Expected: {self.EXPECTED_FORMAT}.",
            )

        if manifest.package_type != self.EXPECTED_PACKAGE_TYPE:

            raise UpgradePackageFormatError(
                f"Unsupported package type: " f"{manifest.package_type}.",
            )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    def _validate_application(
        self,
        manifest: PackageManifest,
    ) -> None:

        if manifest.application.name != self.EXPECTED_APPLICATION:

            raise UpgradeManifestError(
                "Upgrade package is not an Entropy application package.",
            )

    # ------------------------------------------------------------------
    # Python
    # ------------------------------------------------------------------

    def _validate_python(
        self,
        manifest: PackageManifest,
    ) -> None:

        minimum = manifest.application.minimum_python

        if minimum is None:

            return

        try:

            required = Version(
                minimum,
            )

            current = Version(
                ".".join(str(value) for value in sys.version_info[:3]),
            )

        except InvalidVersion as exc:

            raise UpgradeManifestError(
                f"Invalid minimum Python version: {minimum}",
            ) from exc

        if current < required:

            raise UpgradeVersionError(
                f"Entropy {manifest.application.version} "
                f"requires Python >= {minimum}; "
                f"current Python is {current}.",
            )

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------

    def _validate_version(
        self,
        current_version: str,
        target_version: str,
    ) -> None:

        try:

            current = Version(
                current_version,
            )

            target = Version(
                target_version,
            )

        except InvalidVersion as exc:

            raise UpgradeVersionError(
                "Invalid application version.",
            ) from exc

        if target == current:

            raise UpgradeNotRequiredError(
                f"Entropy {target} is already installed.",
            )

        if target < current:

            raise DowngradeNotAllowedError(
                f"Downgrade from Entropy {current} " f"to {target} is not allowed.",
            )

    # ------------------------------------------------------------------
    # Application files
    # ------------------------------------------------------------------

    def _validate_application_files(
        self,
        package: UpgradePackage,
    ) -> None:

        required = (
            "application/entropy.py",
            "application/core",
            "application/lib",
        )

        for path in required:

            if not package.contains(
                path,
            ):

                raise UpgradePackageFormatError(
                    f"Upgrade package is missing " f"required path: {path}",
                )
