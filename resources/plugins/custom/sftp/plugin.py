"""
SFTP transfer plugin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .archive import SftpArchiveBuilder
from .client import SftpClient
from .exceptions import SftpPluginException
from .operations import (
    SftpGetOperation,
    SftpListOperation,
    SftpMkdirOperation,
    SftpPutOperation,
)
from .resolver import SftpResolver
from .transfer import SftpTransfer


class SftpPlugin(
    BasePlugin,
):
    """
    Generic SFTP transfer plugin.
    """

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the SFTP operation.
        """

        self.message.info(
            "Starting sftp.",
        )

        try:
            with self.activity(
                "sftp",
            ):
                result = self._execute()

        except SftpPluginException as exc:
            self.message.error(
                str(exc),
            )

            return PluginResult(
                success=False,
                changed=False,
                outputs=dict(
                    self.outputs,
                ),
                changes=[],
                errors=[str(exc)],
                warnings=[],
                metadata={
                    "artifacts": {
                        name: str(path)
                        for name, path in self.artifacts.items()
                    },
                },
            )

        self.message.success(
            "sftp completed successfully.",
        )

        return PluginResult(
            success=True,
            changed=result["changed"],
            outputs=dict(
                self.outputs,
            ),
            changes=result["changes"],
            errors=[],
            warnings=[],
            metadata={
                "artifacts": {
                    name: str(path)
                    for name, path in self.artifacts.items()
                },
            },
        )

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> dict[str, Any]:
        """
        Resolve arguments and execute the requested operation.
        """

        resolver = SftpResolver()

        request = resolver.resolve(
            self.arguments.as_dict(),
        )

        client = SftpClient(
            request.sftp,
            request.settings,
        )

        archive_builder = SftpArchiveBuilder()

        transfer = SftpTransfer(
            client,
        )

        try:
            client.connect()

            result = self._dispatch(
                request=request,
                client=client,
                archive_builder=archive_builder,
                transfer=transfer,
            )

        finally:
            client.close()

        self._record_result(
            result,
        )

        return result

    def _dispatch(
        self,
        *,
        request: Any,
        client: SftpClient,
        archive_builder: SftpArchiveBuilder,
        transfer: SftpTransfer,
    ) -> dict[str, Any]:
        """
        Dispatch the resolved request to the appropriate operation.
        """

        if request.operation == "put":
            operation = SftpPutOperation(
                client=client,
                archive_builder=archive_builder,
                transfer=transfer,
            )

            return operation.execute(
                request=request,
                workspace=self.workspace,
            )

        if request.operation == "get":
            operation = SftpGetOperation(
                client=client,
                archive_builder=archive_builder,
                transfer=transfer,
            )

            return operation.execute(
                request=request,
                workspace=self.workspace,
            )

        if request.operation == "list":
            operation = SftpListOperation(
                client=client,
            )

            return operation.execute(
                request=request,
            )

        if request.operation == "mkdir":
            operation = SftpMkdirOperation(
                transfer=transfer,
            )

            return operation.execute(
                request=request,
            )

        raise SftpPluginException(
            f"Unsupported SFTP operation: "
            f"{request.operation}",
        )

    # ------------------------------------------------------------------
    # Result handling
    # ------------------------------------------------------------------

    def _record_result(
        self,
        result: dict[str, Any],
    ) -> None:
        """
        Record operation results in plugin outputs and artifacts.
        """

        self.outputs["operation"] = result.get(
            "operation",
        )

        self.outputs["source"] = result.get(
            "source",
        )

        self.outputs["destination"] = result.get(
            "destination",
        )

        self.outputs["files_transferred"] = result.get(
            "files_transferred",
            0,
        )

        self.outputs["entries"] = result.get(
            "entries",
            [],
        )

        archive = result.get(
            "archive",
        )

        if archive:
            archive_path = Path(
                archive,
            )

            if archive_path.is_file():
                self.artifacts["archive"] = archive_path

        result["changed"] = result.get(
            "operation",
        ) in {
            "put",
            "get",
            "mkdir",
        }

        result["changes"] = []

        if result["changed"]:
            result["changes"].append(
                {
                    "operation": result.get(
                        "operation",
                    ),
                    "source": result.get(
                        "source",
                    ),
                    "destination": result.get(
                        "destination",
                    ),
                    "files_transferred": result.get(
                        "files_transferred",
                        0,
                    ),
                },
            )
