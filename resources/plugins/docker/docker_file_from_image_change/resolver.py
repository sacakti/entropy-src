"""
Dockerfile FROM image change configuration resolver.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.plugins.arguments import PluginArguments

from .exceptions import (
    DockerFileFromImageChangePluginException,
)
from .model import (
    DockerFileFromImageChangeConfig,
    DockerfileMapping,
)


class DockerFileFromImageChangeResolver:
    """
    Resolve plugin arguments into normalized configuration.
    """

    def __init__(
        self,
        filesystem,
    ) -> None:

        self.filesystem = filesystem

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def resolve(
        self,
        arguments: PluginArguments,
    ) -> DockerFileFromImageChangeConfig:
        """
        Resolve plugin arguments.
        """

        mode = arguments.string(
            "mode",
            required=True,
        )

        assert mode is not None

        mode = mode.casefold()

        if mode == "direct":

            mappings = self._resolve_direct(
                arguments,
            )

        elif mode == "source":

            mappings = self._resolve_source(
                arguments,
            )

        else:

            raise DockerFileFromImageChangePluginException(
                "Invalid mode. Expected 'direct' or 'source'.",
            )

        if not mappings:

            raise DockerFileFromImageChangePluginException(
                "At least one Dockerfile mapping is required.",
            )

        return DockerFileFromImageChangeConfig(
            mappings=tuple(
                mappings,
            ),
        )

    # ------------------------------------------------------------------
    # Direct
    # ------------------------------------------------------------------

    def _resolve_direct(
        self,
        arguments: PluginArguments,
    ) -> list[DockerfileMapping]:
        """
        Resolve mappings supplied directly by the workflow.
        """

        mappings = arguments.dictionary(
            "mappings",
            required=True,
        )

        assert mappings is not None

        return self._normalize_mappings(
            mappings,
        )

    # ------------------------------------------------------------------
    # Source
    # ------------------------------------------------------------------

    def _resolve_source(
        self,
        arguments: PluginArguments,
    ) -> list[DockerfileMapping]:
        """
        Resolve mappings from a JSON source file.
        """

        source = arguments.path(
            "source",
            required=True,
        )

        assert source is not None

        if not source.is_file():

            raise DockerFileFromImageChangePluginException(
                f"Source file does not exist: {source}",
            )

        suffix = source.suffix.casefold()

        if suffix not in {
            ".json",
            ".yaml",
            ".yml",
        }:

            raise DockerFileFromImageChangePluginException(
                "Unsupported source format. " "Expected JSON, YAML, or YML.",
            )

        if suffix in {
            ".yaml",
            ".yml",
        }:

            raise DockerFileFromImageChangePluginException(
                "YAML source files are not currently supported "
                "because Entropy uses only the Python standard library.",
            )

        try:

            content = self.filesystem.read_text(
                source,
            )

            data = json.loads(
                content,
            )

        except DockerFileFromImageChangePluginException:

            raise

        except Exception as exc:

            raise DockerFileFromImageChangePluginException(
                f"Unable to read source file '{source}': {exc}",
            ) from exc

        if not isinstance(
            data,
            dict,
        ):

            raise DockerFileFromImageChangePluginException(
                "Source file must contain an object mapping " "Dockerfile paths to target images.",
            )

        return self._normalize_mappings(
            data,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_mappings(
        mappings: dict[Any, Any],
    ) -> list[DockerfileMapping]:
        """
        Validate and normalize Dockerfile mappings.
        """

        normalized: list[DockerfileMapping] = []

        for dockerfile, image in mappings.items():

            if not isinstance(
                dockerfile,
                str,
            ):

                raise DockerFileFromImageChangePluginException(
                    "Dockerfile mapping keys must be strings.",
                )

            if not isinstance(
                image,
                str,
            ):

                raise DockerFileFromImageChangePluginException(
                    f"Target image for '{dockerfile}' must be a string.",
                )

            dockerfile = dockerfile.strip()
            image = image.strip()

            if not dockerfile:

                raise DockerFileFromImageChangePluginException(
                    "Dockerfile path cannot be empty.",
                )

            if not image:

                raise DockerFileFromImageChangePluginException(
                    f"Target image for '{dockerfile}' cannot be empty.",
                )

            normalized.append(
                DockerfileMapping(
                    dockerfile=Path(
                        dockerfile,
                    ),
                    image=image,
                ),
            )

        return normalized
