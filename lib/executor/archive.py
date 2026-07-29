"""
Archive operations mixin.

Provides ZIP and TAR archive handling using the Python standard library.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from core.constants import SUPPORTED_ARCHIVES, TAR_MODES
from lib.executor.types import PathLike


class ArchiveMixin:
    """
    Provides archive operations.
    """

    def _archive_type(self, archive: PathLike) -> str:
        name = archive.name.lower()

        for suffix, archive_type in SUPPORTED_ARCHIVES.items():
            if name.endswith(suffix):
                return archive_type

        raise ValueError(f"Unsupported archive format: {archive}")

    def extract(
        self,
        archive: PathLike,
        destination: PathLike,
    ) -> Path:
        """
        Extract an archive.

        Supported formats:
            - .zip
            - .tar
            - .tar.gz
            - .tgz
            - .tar.bz2
            - .tbz2
            - .tar.xz
            - .txz

        Returns
        -------
        Path
            Extraction directory.
        """

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        archive_type = self._archive_type(archive)

        if archive_type == "zip":

            with zipfile.ZipFile(archive) as fp:
                fp.extractall(destination)

        else:

            with tarfile.open(name=archive, mode="r:*") as fp:
                fp.extractall(destination)

        return destination

    def compress(
        self,
        source: PathLike,
        archive: PathLike,
    ) -> Path:
        """
        Create an archive.

        Supported formats:
            - .zip
            - .tar
            - .tar.gz
            - .tgz

        Returns
        -------
        Path
            Archive path.
        """

        archive_type = self._archive_type(archive)

        if archive_type == "zip":

            with zipfile.ZipFile(
                archive,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as fp:

                if source.is_dir():

                    for file in source.rglob("*"):

                        if file.is_file():
                            fp.write(
                                file,
                                file.relative_to(source),
                            )

                else:

                    fp.write(
                        source,
                        source.name,
                    )

            return archive

        with tarfile.open(
            name=archive,
            mode=TAR_MODES[archive_type],
        ) as fp:
            fp.add(source, arcname=source.name)

        return archive
