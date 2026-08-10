"""
Entropy package reader.
"""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile, is_zipfile

from .exceptions import (
    InvalidUpgradePackageError,
    UpgradePackageFormatError,
)
from .manifest import ManifestReader, PackageManifest


class UpgradePackage:
    """
    Represents an Entropy upgrade package.
    """

    MANIFEST = "manifest.json"

    def __init__(
        self,
        source: Path,
    ) -> None:

        self._source = source

        self._validate_source()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def source(self) -> Path:
        return self._source

    def manifest(self) -> PackageManifest:
        """
        Read the package manifest.
        """

        try:

            with ZipFile(
                self._source,
                "r",
            ) as archive:

                try:

                    raw = archive.read(
                        self.MANIFEST,
                    )

                except KeyError as exc:

                    raise InvalidUpgradePackageError(
                        "Upgrade package does not contain " "'manifest.json'.",
                    ) from exc

        except BadZipFile as exc:

            raise UpgradePackageFormatError(
                f"Invalid Entropy package: {self._source}",
            ) from exc

        try:

            data = json.loads(
                raw.decode("utf-8"),
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:

            raise InvalidUpgradePackageError(
                "Upgrade package manifest is not valid JSON.",
            ) from exc

        if not isinstance(
            data,
            dict,
        ):

            raise InvalidUpgradePackageError(
                "Upgrade package manifest must be a JSON object.",
            )

        return ManifestReader().read(
            data,
        )

    def contains(
        self,
        path: str,
    ) -> bool:
        """
        Return whether the package contains a file or directory.
        """

        normalized = path.rstrip("/")

        try:

            with ZipFile(
                self._source,
                "r",
            ) as archive:

                names = archive.namelist()

                #
                # Exact file or directory entry.
                #

                if normalized in names:
                    return True

                if f"{normalized}/" in names:
                    return True

                #
                # Directory may not have an explicit ZIP entry.
                #
                # Some ZIP creators omit directory entries and only
                # store the files underneath the directory.
                #

                prefix = f"{normalized}/"

                return any(name.startswith(prefix) for name in names)

        except BadZipFile as exc:

            raise UpgradePackageFormatError(
                f"Invalid Entropy package: {self._source}",
            ) from exc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_source(self) -> None:
        """
        Validate the package source.
        """

        if not self._source.exists():

            raise InvalidUpgradePackageError(
                f"Upgrade package not found: {self._source}",
            )

        if not self._source.is_file():

            raise InvalidUpgradePackageError(
                f"Upgrade package is not a file: {self._source}",
            )

        if self._source.suffix.lower() != ".epkg":

            raise UpgradePackageFormatError(
                "Upgrade package must use the '.epkg' extension.",
            )

        if not is_zipfile(
            self._source,
        ):

            raise UpgradePackageFormatError(
                f"Invalid Entropy package: {self._source}",
            )

    # Extract
    def extract(
        self,
        destination: Path,
    ) -> None:
        """
        Safely extract the package into a destination directory.
        """

        destination = destination.expanduser().resolve()

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:

            with ZipFile(
                self._source,
                "r",
            ) as archive:

                for member in archive.infolist():

                    target = (destination / member.filename).resolve()

                    try:

                        target.relative_to(
                            destination,
                        )

                    except ValueError as exc:

                        raise UpgradePackageFormatError(
                            f"Unsafe path in upgrade package: " f"{member.filename}",
                        ) from exc

                archive.extractall(
                    destination,
                )

        except BadZipFile as exc:

            raise UpgradePackageFormatError(
                f"Invalid Entropy package: {self._source}",
            ) from exc
