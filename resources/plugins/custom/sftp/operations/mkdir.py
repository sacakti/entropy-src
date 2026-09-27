"""
SFTP mkdir operation.
"""

from __future__ import annotations

from ..exceptions import SftpPluginException
from ..model import SftpRequest
from ..transfer import SftpTransfer


class SftpMkdirOperation:
    """
    Create an SFTP directory recursively.
    """

    def __init__(
        self,
        transfer: SftpTransfer,
    ) -> None:
        self._transfer = transfer

    def execute(
        self,
        request: SftpRequest,
    ) -> dict[str, object]:
        if request.destination is None:
            raise SftpPluginException(
                "SFTP mkdir requires a destination.",
            )

        self._transfer.ensure_remote_directory(
            request.destination,
        )

        return {
            "operation": "mkdir",
            "destination": request.destination,
        }
