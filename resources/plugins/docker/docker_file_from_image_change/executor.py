"""
Dockerfile FROM image change executor.
"""

from __future__ import annotations

import re
from pathlib import Path

from .exceptions import (
    DockerFileFromImageChangePluginException,
)
from .model import (
    DockerFileFromImageChangeConfig,
)


class DockerFileFromImageChangeExecutor:
    """
    Update FROM images in Dockerfiles.
    """

    _FROM_PATTERN = re.compile(
        r"^(\s*FROM\s+)"
        r"(?P<image>\S+)"
        r"(?P<suffix>\s+.*)?$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        filesystem,
        message,
        log,
    ) -> None:

        self.filesystem = filesystem
        self.message = message
        self.log = log

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def execute(
        self,
        config: DockerFileFromImageChangeConfig,
    ) -> dict:
        """
        Update all configured Dockerfiles.

        Returns the deployment/build context.
        """

        changes = []
        images = []

        for mapping in config.mappings:

            change = self._process_dockerfile(
                mapping.dockerfile,
                mapping.image,
            )

            if change is None:
                continue

            changes.append(
                change,
            )

            images.append(
                {
                    "image": mapping.image,
                    "dockerfile": str(
                        mapping.dockerfile,
                    ),
                },
            )

        return {
            "build_required": bool(images),
            "images": images,
            "changes": changes,
        }

    # ------------------------------------------------------------------
    # Dockerfile
    # ------------------------------------------------------------------

    def _process_dockerfile(
        self,
        dockerfile: Path,
        target_image: str,
    ) -> dict | None:
        """
        Update the FROM statement of a Dockerfile.
        """

        if not dockerfile.is_file():

            raise DockerFileFromImageChangePluginException(
                f"Dockerfile does not exist: {dockerfile}",
            )

        try:

            content = self.filesystem.read_text(
                dockerfile,
            )

        except Exception as exc:

            raise DockerFileFromImageChangePluginException(
                f"Unable to read Dockerfile '{dockerfile}': {exc}",
            ) from exc

        lines = content.splitlines(
            keepends=True,
        )

        from_indexes = [
            index
            for index, line in enumerate(lines)
            if self._is_from_statement(line)
        ]

        if not from_indexes:

            raise DockerFileFromImageChangePluginException(
                f"No FROM statement found in Dockerfile: "
                f"{dockerfile}",
            )

        if len(from_indexes) > 1:

            raise DockerFileFromImageChangePluginException(
                f"Multiple FROM statements found in Dockerfile: "
                f"{dockerfile}. Multi-stage Dockerfiles are not "
                f"supported.",
            )

        index = from_indexes[0]

        line = lines[index]

        match = self._FROM_PATTERN.match(
            line.rstrip("\r\n"),
        )

        assert match is not None

        current_image = match.group(
            "image",
        )

        if current_image == target_image:

            self.message.info(
                f"Dockerfile already uses target image: "
                f"{dockerfile}",
            )

            return None

        new_line = self._replace_from_image(
            line,
            target_image,
        )

        lines[index] = new_line

        new_content = "".join(
            lines,
        )

        try:

            self.filesystem.write_text(
                dockerfile,
                new_content,
            )

        except Exception as exc:

            raise DockerFileFromImageChangePluginException(
                f"Unable to update Dockerfile '{dockerfile}': "
                f"{exc}",
            ) from exc

        self.message.info(
            f"Updated base image in {dockerfile}: "
            f"{current_image} -> {target_image}",
        )

        return {
            "dockerfile": str(
                dockerfile,
            ),
            "from": current_image,
            "to": target_image,
        }

    # ------------------------------------------------------------------
    # FROM
    # ------------------------------------------------------------------

    @classmethod
    def _is_from_statement(
        cls,
        line: str,
    ) -> bool:
        """
        Return whether a line is a FROM instruction.
        """

        return cls._FROM_PATTERN.match(
            line.rstrip("\r\n"),
        ) is not None

    @classmethod
    def _replace_from_image(
        cls,
        line: str,
        target_image: str,
    ) -> str:
        """
        Replace only the image portion of a FROM instruction.
        """

        newline = ""

        if line.endswith("\r\n"):
            newline = "\r\n"

        elif line.endswith("\n"):
            newline = "\n"

        elif line.endswith("\r"):
            newline = "\r"

        content = line.rstrip("\r\n")

        match = cls._FROM_PATTERN.match(
            content,
        )

        assert match is not None

        prefix = match.group(
            1,
        )

        suffix = match.group(
            "suffix",
        ) or ""

        return (
            f"{prefix}"
            f"{target_image}"
            f"{suffix}"
            f"{newline}"
        )
