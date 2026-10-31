"""
OpenShift resource index reader.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from .exceptions import ContextBuilderPluginException


class ResourceIndex:
    """
    Read the cached OpenShift resource index.
    """

    INDEX_PATH = ".entropy" "/resource_index.json"

    def __init__(
        self,
        filesystem,
        log,
    ) -> None:

        self._filesystem = filesystem
        self._log = log

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(
        self,
        repository: Path,
    ) -> dict[str, Any]:
        """
        Load the resource index.
        """

        path = repository / self.INDEX_PATH

        if not self._filesystem.exists(path):

            raise ContextBuilderPluginException(
                f"Resource index not found: {path}",
            )

        if not self._filesystem.is_file(path):

            raise ContextBuilderPluginException(
                f"Resource index is not a file: {path}",
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
                f"Unable to read resource index: {path}",
            ) from exc

        if not isinstance(index, dict):

            raise ContextBuilderPluginException(
                "Resource index must contain a JSON object.",
            )

        return index

    # ------------------------------------------------------------------
    # Deployment
    # ------------------------------------------------------------------

    def find_deployment(
        self,
        index: dict[str, Any],
        image_name: str,
    ) -> dict[str, Any] | None:
        """
        Find the deployment containing an image.
        """

        for match in self._containers(
            index,
        ):

            current_name = match["current_image"].rsplit(
                ":",
                1,
            )[0]

            if (
                current_name.endswith(
                    f"/{image_name}",
                )
                or current_name == image_name
            ):

                return match

        return None

    def find_deployments_by_name(
        self,
        index: dict[str, Any],
        name: str,
    ) -> list[dict[str, Any]]:
        """
        Find every deployment container whose image has the given final
        repository component, ignoring registry, namespace, tag and digest.
        """

        return [
            match
            for match in self._containers(
                index,
            )
            if self._image_name(match["current_image"]) == name
        ]

    @staticmethod
    def _image_name(
        image: str,
    ) -> str:

        last = image.strip().split("@", 1)[0].rsplit("/", 1)[-1]

        return last.split(":", 1)[0]

    @staticmethod
    def _containers(
        index: dict[str, Any],
    ) -> Iterator[dict[str, Any]]:
        """
        Yield every indexed deployment container with an image.
        """

        deployments = index.get(
            "deployments",
            {},
        )

        if not isinstance(
            deployments,
            dict,
        ):
            return

        for filename, deployment in deployments.items():

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

                yield {
                    "file": filename,
                    "deployment": deployment.get(
                        "deployment",
                    ),
                    "container": container_name,
                    "current_image": image,
                }

    # ------------------------------------------------------------------
    # Resource
    # ------------------------------------------------------------------

    def find_resource(
        self,
        index: dict[str, Any],
        *,
        kind: str,
        name: str,
    ) -> dict[str, Any] | None:
        """
        Find an OpenShift resource by kind and name.
        """

        resources = index.get(
            "resources",
            {},
        )

        if not isinstance(
            resources,
            dict,
        ):
            return None

        kind_resources = resources.get(
            kind,
            {},
        )

        if not isinstance(
            kind_resources,
            dict,
        ):
            return None

        resource = kind_resources.get(
            name,
        )

        if not isinstance(
            resource,
            dict,
        ):
            return None

        return {
            "file": resource.get(
                "file",
            ),
            "kind": kind,
            "name": name,
        }
