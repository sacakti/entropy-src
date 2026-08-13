"""
ConfigMap/Secret target resource loader.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import UpdateFileError


@dataclass
class TargetFile:
    """
    YAML target file containing one or more resources.
    """

    path: Path
    documents: list[Any]


@dataclass
class TargetResource:
    """
    Loaded ConfigMap or Secret resource.
    """

    kind: str
    name: str
    document: dict[str, Any]
    target_file: TargetFile
    document_index: int


class ConfigMapSecretTargetLoader:
    """
    Load ConfigMap and Secret resources from YAML files.
    """

    EXTENSIONS = {
        ".yaml",
        ".yml",
    }

    TARGET_KINDS = {
        "ConfigMap",
        "Secret",
    }

    def __init__(
        self,
        filesystem,
    ) -> None:

        self._filesystem = filesystem

    # ------------------------------------------------------------------
    # Directory
    # ------------------------------------------------------------------

    def load_directory(
        self,
        directory: Path,
    ) -> list[TargetResource]:
        """
        Load ConfigMap and Secret resources from a directory.
        """

        if not self._filesystem.exists(
            directory,
        ):

            raise UpdateFileError(
                f"Target directory '{directory}' does not exist.",
            )

        if not self._filesystem.is_directory(
            directory,
        ):

            raise UpdateFileError(
                f"Target path '{directory}' is not a directory.",
            )

        resources: list[TargetResource] = []

        for path in self._filesystem.listdir(
            directory,
        ):

            if not self._filesystem.is_file(
                path,
            ):
                continue

            if path.suffix.lower() not in self.EXTENSIONS:
                continue

            resources.extend(
                self.load_file(
                    path,
                ),
            )

        self._validate_unique_targets(
            resources,
        )

        return resources

    # ------------------------------------------------------------------
    # File
    # ------------------------------------------------------------------

    def load_file(
        self,
        path: Path,
    ) -> list[TargetResource]:
        """
        Load all ConfigMap and Secret resources
        from one YAML file.
        """

        if not self._filesystem.exists(
            path,
        ):

            raise UpdateFileError(
                f"Target YAML file '{path}' does not exist.",
            )

        if not self._filesystem.is_file(
            path,
        ):

            raise UpdateFileError(
                f"Target YAML path '{path}' is not a file.",
            )

        try:

            content = self._filesystem.read_text(
                path,
            )

            documents = self._filesystem.load_yaml_documents(
                content,
            )

        except Exception as exc:

            raise UpdateFileError(
                f"Unable to read target YAML file "
                f"'{path}': {exc}",
            ) from exc

        target_file = TargetFile(
            path=path,
            documents=documents,
        )

        resources: list[TargetResource] = []

        for index, document in enumerate(
            documents,
        ):

            if document is None:
                continue

            resources.append(
                self._resource(
                    document,
                    target_file,
                    index,
                ),
            )

        return resources

    # ------------------------------------------------------------------
    # Resource
    # ------------------------------------------------------------------

    def _resource(
        self,
        document: Any,
        target_file: TargetFile,
        document_index: int,
    ) -> TargetResource:
        """
        Validate and create a target resource.
        """

        path = target_file.path

        display_index = document_index + 1

        if not isinstance(
            document,
            dict,
        ):

            raise UpdateFileError(
                f"Invalid target resource in "
                f"'{path}' document {display_index}: "
                "resource must be an object.",
            )

        kind = document.get(
            "kind",
        )

        if kind not in self.TARGET_KINDS:

            raise UpdateFileError(
                f"Unsupported target kind '{kind}' in "
                f"'{path}' document {display_index}. "
                "Expected ConfigMap or Secret.",
            )

        metadata = document.get(
            "metadata",
        )

        if not isinstance(
            metadata,
            dict,
        ):

            raise UpdateFileError(
                f"Target resource '{kind}' in "
                f"'{path}' document {display_index} "
                "must contain metadata.",
            )

        name = metadata.get(
            "name",
        )

        if not isinstance(
            name,
            str,
        ) or not name.strip():

            raise UpdateFileError(
                f"Target resource '{kind}' in "
                f"'{path}' document {display_index} "
                "must contain metadata.name.",
            )

        return TargetResource(
            kind=kind,
            name=name.strip(),
            document=document,
            target_file=target_file,
            document_index=document_index,
        )

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_unique_targets(
        resources: list[TargetResource],
    ) -> None:
        """
        Reject duplicate ConfigMap/Secret resources.
        """

        seen: dict[
            tuple[str, str],
            TargetResource,
        ] = {}

        for resource in resources:

            identity = (
                resource.kind,
                resource.name,
            )

            previous = seen.get(
                identity,
            )

            if previous is None:

                seen[identity] = resource

                continue

            raise UpdateFileError(
                f"Duplicate target resource "
                f"'{resource.kind}/{resource.name}' "
                f"found in "
                f"'{previous.target_file.path}' "
                f"document "
                f"{previous.document_index + 1} and "
                f"'{resource.target_file.path}' "
                f"document "
                f"{resource.document_index + 1}.",
            )
