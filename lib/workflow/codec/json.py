"""
JSON workflow codec.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lib.models.workflow import Workflow
from lib.workflow.exceptions import (
    WorkflowFileNotFoundError,
    WorkflowFileReadError,
    WorkflowFileWriteError,
    WorkflowPathNotFileError,
)

from .structured import StructuredWorkflowCodec

if TYPE_CHECKING:
    from lib.executor.linux import LinuxExecutor


class JsonWorkflowCodec(
    StructuredWorkflowCodec,
):
    """
    JSON workflow codec.

    Workflow mapping and model conversion are implemented
    by StructuredWorkflowCodec.

    LinuxExecutor owns filesystem I/O.
    """

    def __init__(
        self,
        executor: LinuxExecutor,
    ) -> None:

        self._executor = executor

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def format(
        self,
    ) -> str:

        return "json"

    # ------------------------------------------------------------------
    # Decode
    # ------------------------------------------------------------------

    def decode(
        self,
        data: str,
    ) -> Workflow:
        """
        Decode JSON into a Workflow model.
        """

        value = self._executor.parse_json(
            data,
        )

        return self._from_mapping(
            value,
        )

    # ------------------------------------------------------------------
    # Encode
    # ------------------------------------------------------------------

    def encode(
        self,
        workflow: Workflow,
    ) -> str:
        """
        Encode a Workflow as formatted JSON.
        """

        value = self._to_mapping(
            workflow,
        )

        return self._executor.serialize_json(
            value,
        )

    # ------------------------------------------------------------------
    # File Decode
    # ------------------------------------------------------------------

    def decode_file(
        self,
        path: Path,
    ) -> Workflow:
        """
        Read and decode a JSON workflow file.
        """

        path = self._executor.path(
            str(path),
        )

        if not self._executor.exists(
            path,
        ):

            raise WorkflowFileNotFoundError(
                path,
            )

        if not self._executor.is_file(
            path,
        ):

            raise WorkflowPathNotFileError(
                path,
            )

        try:

            data = self._executor.read_text(
                path,
            )

        except OSError as exc:

            raise WorkflowFileReadError(
                path,
            ) from exc

        return self.decode(
            data,
        )

    # ------------------------------------------------------------------
    # File Encode
    # ------------------------------------------------------------------

    def encode_file(
        self,
        workflow: Workflow,
        path: Path,
    ) -> None:
        """
        Write a Workflow to a JSON file.
        """

        path = self._executor.path(
            str(path),
        )

        try:

            self._executor.write_text(
                path,
                self.encode(
                    workflow,
                ),
            )

        except OSError as exc:

            raise WorkflowFileWriteError(
                path,
            ) from exc
