"""
Formatter manager.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from lib.formatter.base import BaseFormatter
from lib.formatter.exceptions import (
    FormatterFileError,
    FormatterFormatError,
)
from lib.formatter.formats.json import JsonFormatter
from lib.formatter.formats.sql import SqlFormatter
from lib.formatter.formats.yaml import YamlFormatter


class FormatterManager:
    """
    Resolve and execute document formatters.
    """

    SUPPORTED_FORMATS = (
        "json",
        "yaml",
        "sql",
    )

    EXTENSIONS = {
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".sql": "sql",
    }

    def __init__(
        self,
    ) -> None:

        self._formatters: dict[str, BaseFormatter] = {}

        self.register(
            JsonFormatter(),
        )

        self.register(
            YamlFormatter(),
        )

        self.register(
            SqlFormatter(),
        )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        formatter: BaseFormatter,
    ) -> None:
        """
        Register a formatter.
        """

        self._formatters[
            formatter.name
        ] = formatter

        for alias in formatter.aliases:

            self._formatters[
                alias
            ] = formatter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format_text(
        self,
        content: str,
        format: str,
    ) -> str:
        """
        Format text using an explicit format.
        """

        formatter = self._get_formatter(
            format,
        )

        return formatter.format(
            content,
        )

    def format_file(
        self,
        source: Path,
        *,
        format: str | None = None,
        destination: Path | None = None,
    ) -> Path:
        """
        Format a file.

        If destination is omitted, the source is replaced in-place.

        If format is omitted, the format is detected from the source
        extension.

        If format is explicitly supplied, it must match the source
        extension.
        """

        source = Path(
            source,
        )

        formatted = self._format_file_content(
            source=source,
            format=format,
        )

        if destination is None:

            self._write_in_place(
                source,
                formatted,
            )

            return source

        destination = Path(
            destination,
        )

        self._write(
            destination,
            formatted,
        )

        return destination

    def format_file_content(
        self,
        source: Path,
        *,
        format: str | None = None,
    ) -> str:
        """
        Format a file and return the formatted content.

        The source file is never modified.
        """

        source = Path(
            source,
        )

        return self._format_file_content(
            source=source,
            format=format,
        )

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_file_content(
        self,
        source: Path,
        *,
        format: str | None = None,
    ) -> str:
        """
        Read and format a source file without writing it.
        """

        self._validate_source(
            source,
        )

        detected_format = self.detect_format(
            source,
        )

        if format is None:

            selected_format = detected_format

        else:

            selected_format = self.normalize_format(
                format,
            )

            if selected_format != detected_format:

                raise FormatterFormatError(
                    f"Explicit format '{selected_format}' does not "
                    f"match source file '{source.name}', which is "
                    f"detected as '{detected_format}'.",
                )

        content = self._read(
            source,
        )

        return self.format_text(
            content,
            selected_format,
        )

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_format(
        self,
        source: Path,
    ) -> str:
        """
        Detect the format from a file extension.
        """

        extension = source.suffix.casefold()

        format = self.EXTENSIONS.get(
            extension,
        )

        if format is None:

            supported = ", ".join(
                self.SUPPORTED_FORMATS,
            )

            raise FormatterFormatError(
                f"Unable to determine format for '{source}'. "
                f"Supported extensions: .json, .yaml, .yml, .sql. "
                f"Supported formats: {supported}.",
            )

        return format

    def normalize_format(
        self,
        format: str,
    ) -> str:
        """
        Normalize a format name.
        """

        normalized = format.strip().casefold()

        if normalized not in self._formatters:

            supported = ", ".join(
                self.SUPPORTED_FORMATS,
            )

            raise FormatterFormatError(
                f"Unsupported format '{format}'. "
                f"Supported formats: {supported}.",
            )

        formatter = self._formatters[
            normalized
        ]

        return formatter.name

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_source(
        source: Path,
    ) -> None:
        """
        Validate source file.
        """

        if not source.exists():

            raise FormatterFileError(
                f"Source file '{source}' does not exist.",
            )

        if not source.is_file():

            raise FormatterFileError(
                f"Source path '{source}' is not a file.",
            )

    # ------------------------------------------------------------------
    # IO
    # ------------------------------------------------------------------

    @staticmethod
    def _read(
        source: Path,
    ) -> str:
        """
        Read source content.
        """

        try:

            return source.read_text(
                encoding="utf-8",
            )

        except OSError as exc:

            raise FormatterFileError(
                f"Unable to read '{source}': {exc}",
            ) from exc

    @staticmethod
    def _write(
        destination: Path,
        content: str,
    ) -> None:
        """
        Write formatted content to destination.
        """

        try:

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            destination.write_text(
                content,
                encoding="utf-8",
            )

        except OSError as exc:

            raise FormatterFileError(
                f"Unable to write '{destination}': {exc}",
            ) from exc

    @staticmethod
    def _write_in_place(
        source: Path,
        content: str,
    ) -> None:
        """
        Atomically replace the source file.
        """

        temporary_path: Path | None = None

        try:

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=source.parent,
                prefix=f".{source.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:

                temporary.write(
                    content,
                )

                temporary.flush()

                os.fsync(
                    temporary.fileno(),
                )

                temporary_path = Path(
                    temporary.name,
                )

            os.replace(
                temporary_path,
                source,
            )

            temporary_path = None

        except OSError as exc:

            raise FormatterFileError(
                f"Unable to replace '{source}': {exc}",
            ) from exc

        finally:

            if temporary_path is not None:

                try:

                    temporary_path.unlink(
                        missing_ok=True,
                    )

                except OSError:

                    pass

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get(
        self,
        format: str,
    ) -> BaseFormatter:
        """
        Return a registered formatter.
        """

        normalized = self.normalize_format(
            format,
        )

        return self._formatters[
            normalized
        ]

    def formats(
        self,
    ) -> tuple[str, ...]:
        """
        Return supported canonical formats.
        """

        return self.SUPPORTED_FORMATS

    def _get_formatter(
        self,
        format: str,
    ) -> BaseFormatter:
        """
        Resolve a formatter.
        """

        normalized = self.normalize_format(
            format,
        )

        return self._formatters[
            normalized
        ]
