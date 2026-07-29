"""
Filesystem operations mixin.

Provides common file and directory operations using pathlib and shutil.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

from lib.executor.types import PathLike


class FileSystemMixin:
    """
    Provides filesystem operations.
    """

    # ------------------------------------------------------------------
    # Existence
    # ------------------------------------------------------------------

    def exists(
        self,
        path: PathLike,
    ) -> bool:
        """
        Return True if the path exists.
        """
        return path.exists()

    def is_file(
        self,
        path: PathLike,
    ) -> bool:
        """
        Return True if the path is a regular file.
        """
        return path.is_file()

    def is_directory(
        self,
        path: PathLike,
    ) -> bool:
        """
        Return True if the path is a directory.
        """
        return path.is_dir()

    # ------------------------------------------------------------------
    # Directory
    # ------------------------------------------------------------------

    def mkdir(
        self,
        path: PathLike,
        parents: bool = True,
        exist_ok: bool = True,
    ) -> Path:
        """
        Create a directory.

        Returns
        -------
        Path
            Created directory.
        """

        path.mkdir(
            parents=parents,
            exist_ok=exist_ok,
        )

        return path

    # ------------------------------------------------------------------
    # Copy / Move
    # ------------------------------------------------------------------

    def copy(
        self,
        source: PathLike,
        destination: PathLike,
    ) -> Path:
        """
        Copy a file or directory.

        Returns
        -------
        Path
            Destination path.
        """

        if source.is_dir():

            shutil.copytree(
                source,
                destination,
                dirs_exist_ok=True,
            )

        else:

            shutil.copy2(
                source,
                destination,
            )

        return destination

    def move(
        self,
        source: PathLike,
        destination: PathLike,
    ) -> Path:
        """
        Move a file or directory.

        Returns
        -------
        Path
            Destination path.
        """

        shutil.move(
            str(source),
            str(destination),
        )

        return destination

    def rename(
        self,
        source: PathLike,
        name: str,
    ) -> Path:
        """
        Rename a file or directory.

        Parameters
        ----------
        source:
            Existing path.

        name:
            New file or directory name.

        Returns
        -------
        Path
            Renamed path.
        """

        destination = source.with_name(name)

        source.rename(destination)

        return destination

    def remove(
        self,
        path: PathLike,
    ) -> Path:
        """
        Remove a file, symbolic link or directory.

        Returns
        -------
        Path
            Removed path.
        """

        if not path.exists():
            return path

        if path.is_symlink():

            path.unlink()

        elif path.is_dir():

            shutil.rmtree(path)

        else:

            path.unlink()

        return path

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def chmod(
        self,
        path: PathLike,
        mode: int,
    ) -> Path:
        """
        Change file permissions.

        Returns
        -------
        Path
            Updated path.
        """

        path.chmod(mode)

        return path

    def symlink(
        self,
        source: PathLike,
        destination: PathLike,
    ) -> Path:
        """
        Create a symbolic link.

        Returns
        -------
        Path
            Symbolic link path.
        """

        destination.symlink_to(source)

        return destination

    # ------------------------------------------------------------------
    # File Content
    # ------------------------------------------------------------------

    def read_text(
        self,
        path: PathLike,
        encoding: str = "utf-8",
    ) -> str:
        """
        Read a UTF-8 text file.
        """

        return path.read_text(
            encoding=encoding,
        )

    def write_text(
        self,
        path: PathLike,
        text: str,
        encoding: str = "utf-8",
    ) -> Path:
        """
        Write text to a file.

        Returns
        -------
        Path
            Updated file.
        """

        path.write_text(
            text,
            encoding=encoding,
        )

        return path

    def append_text(
        self,
        path: PathLike,
        text: str,
        encoding: str = "utf-8",
    ) -> Path:
        """
        Append text to a file.

        Returns
        -------
        Path
            Updated file.
        """

        with path.open(
            "a",
            encoding=encoding,
        ) as fp:

            fp.write(text)

        return path

    def read_json(
        self,
        path: PathLike,
    ):

        return json.loads(self.read_text(path))

    def write_json(
        self,
        path: PathLike,
        data,
        indent: int = 4,
    ):

        return self.write_text(
            path,
            json.dumps(
                data,
                indent=indent,
            ),
        )

    def touch(
        self,
        path: PathLike,
    ) -> Path:
        """
        Create an empty file if it does not exist.

        Returns
        -------
        Path
            File path.
        """

        path.touch(
            exist_ok=True,
        )

        return path

    # ------------------------------------------------------------------
    # Working Directory
    # ------------------------------------------------------------------

    def chdir(
        self,
        path: PathLike,
    ) -> Path:
        """
        Change the current working directory.

        Returns
        -------
        Path
            Current working directory.
        """

        os.chdir(path)

        return path

    def pwd(self) -> Path:
        """
        Return the current working directory.
        """

        return Path.cwd()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def listdir(
        self,
        directory: PathLike,
    ) -> list[Path]:
        """
        Return the immediate contents of a directory.
        """

        return sorted(directory.iterdir())

    def find(
        self,
        directory: PathLike,
        pattern: str = "*",
        recursive: bool = True,
    ) -> list[Path]:
        """
        Find files matching a pattern.
        """

        if recursive:

            return sorted(directory.rglob(pattern))

        return sorted(directory.glob(pattern))

    def walk(
        self,
        directory: PathLike,
    ) -> Iterator[
        tuple[
            Path,
            list[Path],
            list[Path],
        ]
    ]:
        """
        Walk a directory tree.

        Yields
        ------
        tuple
            (directory, subdirectories, files)
        """

        for root, dirs, files in os.walk(directory):

            yield (
                Path(root),
                [Path(root) / d for d in dirs],
                [Path(root) / f for f in files],
            )

    def read_bytes(
        self,
        path: PathLike,
    ) -> bytes:
        """
        Read a binary file.

        Returns
        -------
        bytes
            File contents.
        """

        return path.read_bytes()

    def write_bytes(
        self,
        path: PathLike,
        data: bytes,
    ) -> Path:
        """
        Write binary data to a file.

        Returns
        -------
        Path
            Updated file.
        """

        path.write_bytes(data)

        return path

    def open_text(
        self,
        path: PathLike,
        mode: str = "r",
        encoding: str = "utf-8",
    ):
        """
        Open a text file.

        Returns
        -------
        TextIO
            Open file object.
        """

        return path.open(
            mode=mode,
            encoding=encoding,
        )

    def open_binary(
        self,
        path: PathLike,
        mode: str = "rb",
    ):
        """
        Open a binary file.

        Returns
        -------
        BinaryIO
            Open file object.
        """

        return path.open(mode=mode)
