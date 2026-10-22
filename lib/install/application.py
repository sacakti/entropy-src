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
                    ignore=_ignore_caches,
                )

            else:

                shutil.copy2(
                    item,
                    destination,
                )


def _ignore_caches(directory: str, names: list) -> set:
    """
    Skip byte-code caches, but not byte code that stands in for its source:
    releases ship compiled modules without sources.
    """

    skipped = {name for name in names if name == "__pycache__"}
    for name in names:
        if name.endswith((".pyc", ".pyo")) and name[:-1] in names:
            skipped.add(name)
    return skipped
