"""
Application installer.
"""

from __future__ import annotations

import shutil
from pathlib import Path


class ApplicationInstaller:

    def __init__(
        self,
        source: Path,
        destination: Path,
    ) -> None:

        self._source = source
        self._destination = destination

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def install(self) -> None:
        """
        Install the Entropy application source.
        """

        if not self._source.exists():

            raise FileNotFoundError(
                f"Application source not found: {self._source}",
            )

        if not self._source.is_dir():

            raise ValueError(
                f"Application source is not a directory: {self._source}",
            )

        if self._destination.exists():

            shutil.rmtree(
                self._destination,
            )

        self._destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._copy_tree()

    # ------------------------------------------------------------------
    # Copy
    # ------------------------------------------------------------------

    def _copy_tree(self) -> None:

        excluded = {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            "build",
            "dist",
            "tmp",
            "logs",
            "tests",
        }

        for item in self._source.iterdir():

            if item.name in excluded:
                continue

            destination = self._destination / item.name

            if item.is_dir():

                shutil.copytree(
                    item,
                    destination,
                    ignore=shutil.ignore_patterns(
                        "__pycache__",
                        "*.pyc",
                        "*.pyo",
                    ),
                )

            else:

                shutil.copy2(
                    item,
                    destination,
                )
