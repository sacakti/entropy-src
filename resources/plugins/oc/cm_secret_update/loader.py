"""
ConfigMap/Secret source definition loader.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import UpdateFileError
from .model import (
    ConfigMapSecretResource,
    ConfigMapSecretSource,
    SourceType,
)
from .validator import ConfigMapSecretUpdateValidator


class ConfigMapSecretUpdateLoader:
    """
    Load ConfigMap/Secret source definitions from YAML files.

    Supported source definitions:

    - entropy/v1 ConfigMapSecretUpdate
    - native ConfigMap
    - native Secret
    """

    EXTENSIONS = {
        ".yaml",
        ".yml",
    }

    RESOURCE_KINDS = {
        "ConfigMap",
        "Secret",
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
    ) -> list[ConfigMapSecretSource]:
        """
        Load all source definitions from a directory.
        """

        if not self._filesystem.exists(
            directory,
        ):

            raise UpdateFileError(
                f"Source directory '{directory}' does not exist.",
            )

        if not self._filesystem.is_directory(
            directory,
        ):

            raise UpdateFileError(
                f"Source path '{directory}' is not a directory.",
            )

        sources: list[ConfigMapSecretSource] = []

        for path in sorted(
            self._filesystem.listdir(
                directory,
            ),
        ):

            if not self._filesystem.is_file(
                path,
            ):
                continue

            if path.suffix.lower() not in self.EXTENSIONS:
                continue

            sources.extend(
                self.load_file(
                    path,
                ),
            )

        if not sources:

            raise UpdateFileError(
                f"No YAML source definitions found in "
                f"'{directory}'.",
            )

        return sources

    # ------------------------------------------------------------------
    # Load file
    # ------------------------------------------------------------------

    def load_file(
        self,
        path: Path,
    ) -> list[ConfigMapSecretSource]:
        """
        Load all source definitions from one YAML file.

        A YAML file may contain multiple documents.
        """

        if not self._filesystem.exists(
            path,
        ):

            raise UpdateFileError(
                f"Source YAML file '{path}' does not exist.",
            )

        if not self._filesystem.is_file(
            path,
        ):

            raise UpdateFileError(
                f"Source YAML path '{path}' is not a file.",
            )

        try:

            content = self._filesystem.read_text(
                path,
            )

        except OSError as exc:

            raise UpdateFileError(
                f"Unable to read source YAML file "
                f"'{path}': {exc}",
            ) from exc

        try:

            documents = self._filesystem.load_yaml_documents(
                content,
            )

        except Exception as exc:

            raise UpdateFileError(
                f"Unable to parse source YAML file "
                f"'{path}': {exc}",
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

        sources: list[ConfigMapSecretSource] = []

        for index, document in enumerate(
            documents,
            start=1,
        ):

            if document is None:
                continue

            try:

                source = self._parse_document(
                    document,
                    path,
                )

            except Exception as exc:

                raise UpdateFileError(
                    f"Invalid source definition in "
                    f"'{path}' document {index}: {exc}",
                ) from exc

            sources.append(
                source,
            )

        return sources

    # ------------------------------------------------------------------
    # Document
    # ------------------------------------------------------------------

    def _parse_document(
        self,
        document: Any,
        path: Path,
    ) -> ConfigMapSecretSource:
        """
        Parse one source document.

        Entropy update definitions and native Kubernetes resources
        are intentionally handled separately.
        """

        if not isinstance(
            document,
            dict,
        ):

            raise UpdateFileError(
                "Source document must be an object.",
            )

        kind = document.get(
            "kind",
        )

        if kind in self.RESOURCE_KINDS:

            return self._native_resource(
                document,
                path,
            )

        if (
            document.get("apiVersion")
            == ConfigMapSecretUpdateValidator.API_VERSION
            and kind
            == ConfigMapSecretUpdateValidator.KIND
        ):

            definition = ConfigMapSecretUpdateValidator.parse(
                document,
            )

            return ConfigMapSecretSource(
                source_type=SourceType.UPDATE,
                path=path,
                update=definition,
            )

        raise UpdateFileError(
            f"Unsupported source kind '{kind}'. "
            "Expected ConfigMapSecretUpdate, "
            "ConfigMap, or Secret.",
        )

    # ------------------------------------------------------------------
    # Native resource
    # ------------------------------------------------------------------

    @staticmethod
    def _native_resource(
        document: dict[str, Any],
        path: Path,
    ) -> ConfigMapSecretSource:
        """
        Parse a native ConfigMap or Secret resource.
        """

        kind = document.get(
            "kind",
        )

        if kind not in {
            "ConfigMap",
            "Secret",
        }:

            raise UpdateFileError(
                f"Unsupported native resource kind '{kind}'.",
            )

        api_version = document.get(
            "apiVersion",
        )

        if (
            not isinstance(
                api_version,
                str,
            )
            or not api_version.strip()
        ):

            raise UpdateFileError(
                f"Native {kind} '{path}' "
                "must contain apiVersion.",
            )

        metadata = document.get(
            "metadata",
        )

        if not isinstance(
            metadata,
            dict,
        ):

            raise UpdateFileError(
                f"Native {kind} resource must contain metadata.",
            )

        name = metadata.get(
            "name",
        )

        if (
            not isinstance(
                name,
                str,
            )
            or not name.strip()
        ):

            raise UpdateFileError(
                f"Native {kind} resource must contain "
                "metadata.name.",
            )

        return ConfigMapSecretSource(
            source_type=SourceType.RESOURCE,
            path=path,
            resource=ConfigMapSecretResource(
                api_version=api_version,
                kind=kind,
                name=name.strip(),
                document=document,
            ),
        )
