"""
Information operations mixin.

Provides file metadata and checksum utilities.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from lib.executor.exceptions import LinuxExceptions
from lib.executor.types import PathLike


class InformationMixin:
    """
    Provides file information operations.
    """

    def stat(
        self,
        path: PathLike,
    ):
        """
        Return filesystem metadata.

        Parameters
        ----------
        path:
            File or directory.

        Returns
        -------
        os.stat_result
            Filesystem metadata.
        """

        return path.stat()

    def checksum(
        self,
        path: PathLike,
        algorithm: str = "sha256",
        chunk_size: int = 1024 * 1024,
    ) -> str:
        """
        Calculate the checksum of a file.

        Parameters
        ----------
        path:
            File to hash.

        algorithm:
            Hash algorithm supported by hashlib.

        chunk_size:
            Number of bytes read per iteration.

        Returns
        -------
        str
            Hexadecimal digest.
        """

        try:
            digest = hashlib.new(algorithm)
        except ValueError as exc:
            raise LinuxExceptions(f"Unsupported hash algorithm: {algorithm}") from exc

        with path.open("rb") as fp:
            while chunk := fp.read(chunk_size):
                digest.update(chunk)

        return digest.hexdigest()

    def md5(self, path: Path) -> str:
        return self.checksum(path, "md5")

    def sha1(self, path: Path) -> str:
        return self.checksum(path, "sha1")

    def sha256(self, path: Path) -> str:
        return self.checksum(path, "sha256")
