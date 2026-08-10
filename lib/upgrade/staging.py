"""
Upgrade package staging.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import mkdtemp

from .exceptions import InvalidUpgradePackageError
from .package import UpgradePackage


class UpgradeStager:
    """
    Extracts an upgrade package into an isolated staging directory.
    """

    def __init__(
        self,
        root: Path | None = None,
    ) -> None:

        self._root = root.expanduser().resolve() if root is not None else None

        self._directory: Path | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def directory(self) -> Path:
        """
        Return the active staging directory.
        """

        if self._directory is None:

            raise RuntimeError(
                "Upgrade staging has not been created.",
            )

        return self._directory

    @property
    def application(self) -> Path:
        """
        Return the staged application directory.
        """

        return self.directory / "application"

    def stage(
        self,
        package: UpgradePackage,
    ) -> Path:
        """
        Extract an upgrade package into staging.
        """

        self.cleanup()

        self._directory = Path(
            mkdtemp(
                prefix="entropy-upgrade-",
                dir=(str(self._root) if self._root is not None else None),
            ),
        )

        try:

            package.extract(
                self._directory,
            )

            self._validate()

            return self._directory

        except Exception:

            self.cleanup()

            raise

    def cleanup(self) -> None:
        """
        Remove the staging directory.
        """

        if self._directory is None:

            return

        if self._directory.exists():

            shutil.rmtree(
                self._directory,
            )

        self._directory = None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        """
        Validate the extracted application.
        """

        if not self.application.exists():

            raise InvalidUpgradePackageError(
                "Staged package does not contain " "an application directory.",
            )

        if not self.application.is_dir():

            raise InvalidUpgradePackageError(
                "Staged application path is not a directory.",
            )

        required = (
            self.application / "entropy.py",
            self.application / "core",
            self.application / "lib",
        )

        for path in required:

            if not path.exists():

                raise InvalidUpgradePackageError(
                    f"Staged application is missing: {path}",
                )
