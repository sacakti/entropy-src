"""
SFTP get operation.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import shutil
from uuid import uuid4

from ..exceptions import SftpPluginException
from ..archive import SftpArchiveBuilder
from ..client import SftpClient
from ..model import SftpRequest
from ..transfer import SftpTransfer


class SftpGetOperation:
    """
    Execute an SFTP-to-local transfer.
    """

    def __init__(
        self,
        client: SftpClient,
        archive_builder: SftpArchiveBuilder,
        transfer: SftpTransfer,
    ) -> None:
        self._client = client
        self._archive_builder = archive_builder
        self._transfer = transfer

    def execute(
        self,
        request: SftpRequest,
        workspace: Path,
    ) -> dict[str, object]:
        if request.source is None:
            raise SftpPluginException(
                "SFTP get requires a source.",
            )

        if request.destination is None:
            raise SftpPluginException(
                "SFTP get requires a destination.",
            )

        source = request.source

        if request.archive.enabled:
            staging = workspace / (
                f".sftp_get_{uuid4().hex}"
            )

            staging.mkdir(
                parents=True,
                exist_ok=False,
            )

            try:
                downloaded = self._transfer.get(
                    source=source,
                    destination=staging,
                )

                archive = self._archive_builder.create(
                    source=staging,
                    workspace=workspace,
                    filename_policy=request.archive.filename_policy,
                )

            finally:
                self._remove_tree(staging)

            destination = Path(
                request.destination,
            ).expanduser()

            destination.mkdir(
                parents=True,
                exist_ok=True,
            )

            final_path = destination / archive.name

            if final_path.exists():
                raise SftpPluginException(
                    f"Destination archive already exists: "
                    f"{final_path}",
                )

            shutil.copy2(
                archive,
                final_path,
            )

            return {
                "operation": "get",
                "source": source,
                "destination": str(final_path),
                "archive": str(final_path),
                "files_transferred": downloaded,
            }

        destination = Path(
            request.destination or "",
        ).expanduser()

        count = self._transfer.get(
            source=source,
            destination=destination,
        )

        return {
            "operation": "get",
            "source": source,
            "destination": str(destination),
            "archive": None,
            "files_transferred": count,
        }

    @staticmethod
    def _remove_tree(
        path: Path,
    ) -> None:
        import shutil

        shutil.rmtree(
            path,
            ignore_errors=True,
        )
