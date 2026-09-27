"""
SFTP recursive transfer utilities.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from .client import SftpClient
from .exceptions import SftpPluginException


class SftpTransfer:
    """
    Handle local-to-SFTP and SFTP-to-local transfers.
    """

    def __init__(
        self,
        client: SftpClient,
    ) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # PUT
    # ------------------------------------------------------------------

    def put(
        self,
        *,
        source: Path,
        destination: str,
    ) -> int:
        """
        Upload a local file or directory recursively.

        Returns the number of files transferred.
        """

        self._validate_local_source(source)

        if source.is_file():
            remote_file = self._remote_file_path(
                destination,
                source.name,
            )

            self._ensure_remote_parent(
                remote_file,
            )

            self._client.upload(
                source,
                remote_file,
            )

            return 1

        return self._put_directory(
            source=source,
            destination=destination,
        )

    def _put_directory(
        self,
        *,
        source: Path,
        destination: str,
    ) -> int:
        """
        Recursively upload a local directory.
        """

        count = 0

        # Create the root destination first.
        self._ensure_remote_directory(
            destination,
        )

        for path in sorted(
            source.rglob("*"),
        ):
            if path.is_symlink():
                continue

            relative = path.relative_to(
                source,
            )

            remote_path = self._remote_file_path(
                destination,
                relative.as_posix(),
            )

            if path.is_dir():
                self._ensure_remote_directory(
                    remote_path,
                )
                continue

            if not path.is_file():
                continue

            self._ensure_remote_parent(
                remote_path,
            )

            self._client.upload(
                path,
                remote_path,
            )

            count += 1

        return count

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def get(
        self,
        *,
        source: str,
        destination: Path,
    ) -> int:
        """
        Download a remote file or directory recursively.

        Returns the number of files transferred.
        """

        attributes = self._client.stat(
            source,
        )

        if self._is_directory(attributes):
            return self._get_directory(
                source=source,
                destination=destination,
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._client.download(
            source,
            destination,
        )

        return 1

    def _get_directory(
        self,
        *,
        source: str,
        destination: Path,
    ) -> int:
        """
        Recursively download a remote directory.
        """

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        count = 0

        for entry in self._client.open_directory(
            source,
        ):
            remote_path = self._remote_file_path(
                source,
                entry.filename,
            )

            local_path = destination / entry.filename

            if self._is_directory(entry):
                count += self._get_directory(
                    source=remote_path,
                    destination=local_path,
                )
                continue

            local_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            self._client.download(
                remote_path,
                local_path,
            )

            count += 1

        return count

    # ------------------------------------------------------------------
    # Remote directory handling
    # ------------------------------------------------------------------

    def ensure_remote_directory(
        self,
        path: str,
    ) -> None:
        """
        Create a remote directory and all missing parents.
        """

        self._ensure_remote_directory(path)

    def _ensure_remote_parent(
        self,
        remote_path: str,
    ) -> None:
        parent = str(
            PurePosixPath(
                remote_path,
            ).parent,
        )

        if parent in {"", "."}:
            return

        self._ensure_remote_directory(
            parent,
        )

    def _ensure_remote_directory(
        self,
        path: str,
    ) -> None:
        """
        Create a remote directory and all missing parents.
        """

        normalized = str(
            PurePosixPath(path),
        )

        if normalized in {"", "."}:
            return

        if normalized == "/":
            return

        if self._remote_directory_exists(
            normalized,
        ):
            return

        parent = str(
            PurePosixPath(normalized).parent,
        )

        if parent not in {"", ".", normalized}:
            self._ensure_remote_directory(
                parent,
            )

        if self._remote_directory_exists(
            normalized,
        ):
            return

        self._client.mkdir(
            normalized,
        )

    def _remote_directory_exists(
        self,
        path: str,
    ) -> bool:
        try:
            attributes = self._client.stat(
                path,
            )
        except SftpPluginException:
            return False

        return self._is_directory(
            attributes,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_local_source(
        source: Path,
    ) -> None:
        if not source.exists():
            raise SftpPluginException(
                f"Source does not exist: {source}",
            )

        if not source.is_file() and not source.is_dir():
            raise SftpPluginException(
                f"Source is not a file or directory: "
                f"{source}",
            )

    @staticmethod
    def _remote_file_path(
        base: str,
        relative: str,
    ) -> str:
        base_path = PurePosixPath(
            base,
        )

        relative_path = PurePosixPath(
            relative,
        )

        if str(base_path) == "/":
            return str(
                PurePosixPath(
                    "/",
                    relative_path,
                ),
            )

        return str(
            base_path / relative_path,
        )

    @staticmethod
    def _is_directory(
        attributes: object,
    ) -> bool:
        """
        Determine whether SFTP attributes represent a directory.
        """

        mode = getattr(
            attributes,
            "st_mode",
            None,
        )

        if mode is None:
            return False

        # S_ISDIR is intentionally imported here to keep the
        # transfer layer independent from Paramiko's types.
        from stat import S_ISDIR

        return S_ISDIR(mode)
