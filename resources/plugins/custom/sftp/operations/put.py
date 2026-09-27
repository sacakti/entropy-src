"""
SFTP put operation.
"""

from __future__ import annotations

from pathlib import Path

from ..exceptions import SftpPluginException
from ..archive import SftpArchiveBuilder
from ..client import SftpClient
from ..model import SftpRequest
from ..transfer import SftpTransfer


class SftpPutOperation:
    """
    Execute a local-to-SFTP transfer.
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
                "SFTP put requires a source.",
            )

        source = Path(
            request.source,
        ).expanduser()

        if request.archive.enabled:
            archive = self._archive_builder.create(
                source=source,
                workspace=workspace,
                filename_policy=request.archive.filename_policy,
            )

            remote_path = self._remote_archive_path(
                request.destination or "/",
                archive.name,
            )

            self._client.upload(
                archive,
                remote_path,
            )

            return {
                "operation": "put",
                "source": str(source),
                "destination": remote_path,
                "archive": str(archive),
                "files_transferred": 1,
            }

        count = self._transfer.put(
            source=source,
            destination=request.destination or "/",
        )

        return {
            "operation": "put",
            "source": str(source),
            "destination": request.destination,
            "archive": None,
            "files_transferred": count,
        }

    @staticmethod
    def _remote_archive_path(
        destination: str,
        filename: str,
    ) -> str:
        from pathlib import PurePosixPath

        return str(
            PurePosixPath(destination) / filename,
        )
