"""Deployment target YAML loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import DeploymentUpdateFileError


@dataclass
class DeploymentTargetFile:
    """YAML file containing one or more resources."""

    path: Path
    documents: list[Any]


@dataclass
class DeploymentTarget:
    """Loaded Deployment resource."""

    kind: str
    name: str
    document: dict[str, Any]
    target_file: DeploymentTargetFile
    document_index: int


class DeploymentTargetLoader:
    """Load Deployment resources from YAML files."""

    EXTENSIONS = {".yaml", ".yml"}

    def __init__(self, filesystem) -> None:
        self._filesystem = filesystem

    def load_file(self, path: Path) -> list[DeploymentTarget]:
        if not self._filesystem.exists(path):
            raise DeploymentUpdateFileError(
                f"Target YAML file '{path}' does not exist.",
            )
        if not self._filesystem.is_file(path):
            raise DeploymentUpdateFileError(
                f"Target YAML path '{path}' is not a file.",
            )

        try:
            documents = self._filesystem.load_yaml_documents(
                self._filesystem.read_text(path),
            )
        except Exception as exc:
            raise DeploymentUpdateFileError(
                f"Unable to read target YAML file '{path}': {exc}",
            ) from exc

        target_file = DeploymentTargetFile(path=path, documents=documents or [])
        targets: list[DeploymentTarget] = []

        for index, document in enumerate(target_file.documents):
            if document is None:
                continue
            if not isinstance(document, dict):
                raise DeploymentUpdateFileError(
                    f"Invalid resource in '{path}' document {index + 1}.",
                )
            if document.get("kind") != "Deployment":
                continue
            metadata = document.get("metadata")
            if not isinstance(metadata, dict) or not isinstance(metadata.get("name"), str):
                raise DeploymentUpdateFileError(
                    f"Deployment in '{path}' document {index + 1} must contain metadata.name.",
                )
            targets.append(
                DeploymentTarget(
                    kind="Deployment",
                    name=metadata["name"].strip(),
                    document=document,
                    target_file=target_file,
                    document_index=index,
                ),
            )
        return targets
