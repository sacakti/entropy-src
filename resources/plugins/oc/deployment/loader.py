"""Deployment update definition loader."""

from __future__ import annotations

from pathlib import Path

from .exceptions import DeploymentUpdateFileError
from .model import DeploymentUpdate
from .validator import DeploymentUpdateValidator


class DeploymentUpdateLoader:
    """Load DeploymentUpdate definitions from YAML files."""

    EXTENSIONS = {".yaml", ".yml"}

    def __init__(self, filesystem) -> None:
        self._filesystem = filesystem

    def load_directory(self, directory: Path) -> list[DeploymentUpdate]:
        if not self._filesystem.exists(directory):
            raise DeploymentUpdateFileError(
                f"Source directory '{directory}' does not exist.",
            )
        if not self._filesystem.is_directory(directory):
            raise DeploymentUpdateFileError(
                f"Source path '{directory}' is not a directory.",
            )

        definitions: list[DeploymentUpdate] = []
        for path in sorted(self._filesystem.listdir(directory)):
            if not self._filesystem.is_file(path):
                continue
            if path.suffix.lower() not in self.EXTENSIONS:
                continue
            definitions.extend(self.load_file(path))

        if not definitions:
            raise DeploymentUpdateFileError(
                f"No YAML update definitions found in '{directory}'.",
            )
        return definitions

    def load_file(self, path: Path) -> list[DeploymentUpdate]:
        if not self._filesystem.exists(path):
            raise DeploymentUpdateFileError(
                f"Source YAML file '{path}' does not exist.",
            )
        if not self._filesystem.is_file(path):
            raise DeploymentUpdateFileError(
                f"Source YAML path '{path}' is not a file.",
            )

        try:
            documents = self._filesystem.load_yaml_documents(
                self._filesystem.read_text(path),
            )
        except Exception as exc:
            raise DeploymentUpdateFileError(
                f"Unable to read source YAML file '{path}': {exc}",
            ) from exc

        definitions: list[DeploymentUpdate] = []
        for index, document in enumerate(documents or [], start=1):
            if document is None:
                continue
            try:
                definitions.append(DeploymentUpdateValidator.parse(document))
            except Exception as exc:
                raise DeploymentUpdateFileError(
                    f"Invalid update definition in '{path}' document {index}: {exc}",
                ) from exc
        return definitions
