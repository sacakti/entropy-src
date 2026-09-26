"""
SQL analysis file scanner.
"""

from __future__ import annotations

from pathlib import Path


class AnalyseScanner:
    """
    Discover SQL script files for analysis.
    """

    DEFAULT_EXCLUDED_DIRECTORIES = (
        ".entropy",
    )

    def scan(
        self,
        path: Path,
        extensions: tuple[str, ...],
    ) -> list[Path]:
        """
        Recursively discover files matching the configured extensions.
        """

        normalized_extensions = {
            extension.casefold()
            for extension in extensions
        }

        excluded_directories = {
            directory.casefold()
            for directory in self.DEFAULT_EXCLUDED_DIRECTORIES
        }

        files = [
            file
            for file in path.rglob("*")
            if file.is_file()
            and file.suffix.casefold() in normalized_extensions
            and not self._is_excluded(
                file,
                path,
                excluded_directories,
            )
        ]

        return sorted(
            files,
            key=lambda file: str(file).casefold(),
        )

    @staticmethod
    def _is_excluded(
        file: Path,
        root: Path,
        excluded_directories: set[str],
    ) -> bool:
        """
        Determine whether a file belongs to an excluded directory.
        """

        try:
            relative_path = file.relative_to(root)
        except ValueError:
            return False

        return any(
            part.casefold() in excluded_directories
            for part in relative_path.parts[:-1]
        )
