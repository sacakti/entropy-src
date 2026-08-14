"""
ConfigMap/Secret update definition loader.
"""

from __future__ import annotations

from pathlib import Path

from .exceptions import UpdateFileError
from .model import ConfigMapSecretUpdate
from .validator import ConfigMapSecretUpdateValidator


class ConfigMapSecretUpdateLoader:
    """
    Load ConfigMap/Secret update definitions from YAML files.
    """

    EXTENSIONS = {
        ".yaml",
        ".yml",
    }

    def __init__(
        self,
        filesystem,
    ) -> None:

        self._filesystem = filesystem

    # ------------------------------------------------------------------
    # Load directory
    # ------------------------------------------------------------------

    def load_directory(
        self,
        directory: Path,
    ) -> list[ConfigMapSecretUpdate]:
        """
        Load all update definitions from a directory.
        """

        if not directory.exists():

            raise UpdateFileError(
                f"Source directory '{directory}' does not exist.",
            )

        if not directory.is_dir():

            raise UpdateFileError(
                f"Source path '{directory}' is not a directory.",
            )

        definitions: list[ConfigMapSecretUpdate] = []

        for path in sorted(
            directory.iterdir(),
        ):

            if not path.is_file():
                continue

            if path.suffix.lower() not in self.EXTENSIONS:
                continue

            definitions.extend(
                self.load_file(
                    path,
                ),
            )

        if not definitions:

            raise UpdateFileError(
                f"No YAML update definitions found in " f"'{directory}'.",
            )

        return definitions

    # ------------------------------------------------------------------
    # Load file
    # ------------------------------------------------------------------

    def load_file(
        self,
        path: Path,
    ) -> list[ConfigMapSecretUpdate]:
        """
        Load all update definitions from one YAML file.
        """

        if not path.exists():

            raise UpdateFileError(
                f"Source YAML file '{path}' does not exist.",
            )

        if not path.is_file():

            raise UpdateFileError(
                f"Source YAML path '{path}' is not a file.",
            )

        try:

            content = path.read_text(
                encoding="utf-8",
            )

        except OSError as exc:

            raise UpdateFileError(
                f"Unable to read source YAML file " f"'{path}': {exc}",
            ) from exc

        try:

            documents = self._filesystem.load_yaml_documents(
                content,
            )

        except Exception as exc:

            raise UpdateFileError(
                f"Unable to parse source YAML file " f"'{path}': {exc}",
            ) from exc

        if documents is None:

            return []

        if not isinstance(
            documents,
            list,
        ):

            documents = [
                documents,
            ]

        definitions: list[ConfigMapSecretUpdate] = []

        for index, document in enumerate(
            documents,
            start=1,
        ):

            if document is None:
                continue

            try:

                definition = ConfigMapSecretUpdateValidator.parse(
                    document,
                )

            except Exception as exc:

                raise UpdateFileError(
                    f"Invalid update definition in " f"'{path}' document {index}: {exc}",
                ) from exc

            definitions.append(
                definition,
            )

        return definitions
