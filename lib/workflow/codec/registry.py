"""
Workflow codec registry.
"""

from __future__ import annotations

from pathlib import Path

from lib.workflow.exceptions import WorkflowFormatError

from .base import WorkflowCodec


class WorkflowCodecRegistry:
    """
    Registry for workflow serialization codecs.

    Resolves the appropriate codec from a workflow file
    extension or an explicitly requested format.
    """

    def __init__(
        self,
        codecs: list[WorkflowCodec],
    ) -> None:

        self._codecs = {codec.format.lower(): codec for codec in codecs}

        self._extensions = {
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
        }

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get(
        self,
        format: str,
    ) -> WorkflowCodec:
        """
        Return a codec by format name.
        """

        key = format.strip().lower()

        codec = self._codecs.get(
            key,
        )

        supported = self.formats()

        if codec is None:

            raise WorkflowFormatError(
                f"Unsupported workflow file extension "
                f"'{format}'. Supported extensions: {supported}.",
            )

        return codec

    def for_path(
        self,
        path: Path,
    ) -> WorkflowCodec:
        """
        Return the codec appropriate for a workflow file.
        """

        suffix = Path(
            path,
        ).suffix.lower()

        format = self._extensions.get(
            suffix,
        )

        if format is None:

            supported = ", ".join(
                sorted(
                    self._extensions,
                ),
            )

            raise WorkflowFormatError(
                f"Unsupported workflow file extension"
                f"'{suffix}'. Supported extensions: {supported}.",
            )

        return self.get(
            format,
        )

    def formats(
        self,
    ) -> list[str]:
        """
        Return supported workflow formats.
        """

        return sorted(
            self._codecs,
        )

    def extensions(
        self,
    ) -> list[str]:
        """
        Return supported workflow file extensions.
        """

        return sorted(
            self._extensions,
        )
