"""
SFTP list operation.
"""

from __future__ import annotations

from ..exceptions import SftpPluginException
from ..client import SftpClient
from ..model import SftpRequest


class SftpListOperation:
    """
    List a remote SFTP directory.
    """

    def __init__(
        self,
        client: SftpClient,
    ) -> None:
        self._client = client

    def execute(
        self,
        request: SftpRequest,
    ) -> dict[str, object]:
        if request.source is None:
            raise SftpPluginException(
                "SFTP list requires a source.",
            )

        entries = self._client.listdir(
            request.source,
        )

        return {
            "operation": "list",
            "source": request.source,
            "entries": entries,
            "count": len(entries),
        }
