"""
Deployment index reader.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .exceptions import ContextBuilderPluginException


class DeploymentIndex:
    """
    Read the cached deployment index.
    """

    INDEX_PATH = (
        ".entropy"
        "/deployment_index.json"
    )

    def __init__(
        self,
        filesystem,
        log,
    ) -> None:

        self._filesystem = filesystem
        self._log = log

    def load(
        self,
        repository: Path,
    ) -> dict[str, Any]:
        """
        Load the deployment index.
        """

        path = (
            repository
            / self.INDEX_PATH
        )

        if not self._filesystem.exists(
            path,
        ):

            raise ContextBuilderPluginException(
                f"Deployment index not found: {path}",
            )

        if not self._filesystem.is_file(
            path,
        ):

            raise ContextBuilderPluginException(
                f"Deployment index is not a file: {path}",
            )

        try:

            content = self._filesystem.read_text(
                path,
            )

            index = json.loads(
                content,
            )

        except (
            OSError,
            ValueError,
        ) as exc:

            raise ContextBuilderPluginException(
                f"Unable to read deployment index: {path}",
            ) from exc

        if not isinstance(
            index,
            dict,
        ):

            raise ContextBuilderPluginException(
                "Deployment index must contain a JSON object.",
            )

        return index

    def find(
        self,
        index: dict[str, Any],
        image_name: str,
    ) -> dict[str, Any] | None:
        """
        Find the deployment containing an image.
        """

        for filename, deployment in index.items():

            if not isinstance(
                deployment,
                dict,
            ):

                continue

            containers = deployment.get(
                "containers",
                {},
            )

            if not isinstance(
                containers,
                dict,
            ):

                continue

            for container_name, container in containers.items():

                if not isinstance(
                    container,
                    dict,
                ):

                    continue

                image = container.get(
                    "image",
                )

                if not isinstance(
                    image,
                    str,
                ):

                    continue

                current_name = image.rsplit(
                    ":",
                    1,
                )[0]

                if current_name.endswith(
                    f"/{image_name}",
                ) or current_name == image_name:

                    return {
                        "file": filename,
                        "deployment": deployment.get(
                            "deployment",
                        ),
                        "container": container_name,
                        "current_image": image,
                    }

        return None
