"""
Release change detection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


class ReleaseChangeDetector:
    """
    Detect changes between release content and repository content.
    """

    def __init__(
        self,
        filesystem,
    ) -> None:

        self._filesystem = filesystem

    def file_changed(
        self,
        source: Path,
        target: Path,
    ) -> bool:
        """
        Return True when source and target differ.
        """

        if not self._filesystem.exists(
            target,
        ):

            return True

        if not self._filesystem.is_file(
            target,
        ):

            return True

        return self._hash(source) != self._hash(target)

    def directory_changed(
        self,
        source: Path,
        target: Path,
        *,
        extensions: set[str] | None = None,
    ) -> bool:
        """
        Compare selected files in two directories.
        """

        source_files = self._files(
            source,
            extensions=extensions,
        )

        target_files = self._files(
            target,
            extensions=extensions,
        )

        source_names = {path.relative_to(source) for path in source_files}

        target_names = {path.relative_to(target) for path in target_files}

        if source_names != target_names:

            return True

        for relative in source_names:

            source_file = source / relative
            target_file = target / relative

            if self.file_changed(
                source_file,
                target_file,
            ):

                return True

        return False

    def _files(
        self,
        root: Path,
        *,
        extensions: set[str] | None = None,
    ) -> list[Path]:
        """
        Find files while ignoring platform metadata.
        """

        if not self._filesystem.exists(
            root,
        ):

            return []

        result = []

        for path in self._filesystem.find(
            root,
            pattern="*",
            recursive=True,
        ):

            if self._ignored(
                path,
            ):

                continue

            if not self._filesystem.is_file(
                path,
            ):

                continue

            if extensions is not None:

                if path.suffix.casefold() not in {extension.casefold() for extension in extensions}:

                    continue

            result.append(
                path,
            )

        return sorted(
            result,
        )

    @staticmethod
    def _ignored(
        path: Path,
    ) -> bool:
        """
        Ignore macOS metadata.
        """

        return (
            path.name == "__MACOSX"
            or path.name == ".DS_Store"
            or path.name.startswith("._")
            or path.name.startswith(".gitignore")
        )

    def _hash(
        self,
        path: Path,
    ) -> str:
        """
        Calculate SHA-256 for a file.
        """

        return hashlib.sha256(
            self._filesystem.read_bytes(
                path,
            ),
        ).hexdigest()
