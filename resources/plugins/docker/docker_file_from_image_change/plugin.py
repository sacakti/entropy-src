"""
Dockerfile FROM image change plugin.
"""

from __future__ import annotations

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import (
    DockerFileFromImageChangePluginException,
)
from .executor import DockerFileFromImageChangeExecutor
from .resolver import DockerFileFromImageChangeResolver


class DockerFileFromImageChangePlugin(
    BasePlugin,
):
    """
    Update base images in Dockerfiles.
    """

    def execute(
        self,
    ) -> PluginResult:
        """
        Resolve configuration and update Dockerfiles.
        """

        self.message.info(
            "Starting docker_file_from_image_change.",
        )

        try:

            with self.activity(
                "docker_file_from_image_change",
            ):

                result = self._execute()

        except DockerFileFromImageChangePluginException as exc:

            self.log.error(
                str(exc),
            )

            self.message.error(
                str(exc),
            )

            return self._result(
                success=False,
                changed=False,
                errors=[
                    str(exc),
                ],
            )

        except Exception as exc:

            self.log.error(
                str(exc),
            )

            self.message.error(
                str(exc),
            )

            return self._result(
                success=False,
                changed=False,
                errors=[
                    str(exc),
                ],
            )

        self.message.success(
            "docker_file_from_image_change completed successfully.",
        )

        return result

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:
        """
        Resolve arguments and update Dockerfiles.
        """

        resolver = DockerFileFromImageChangeResolver(
            filesystem=self.filesystem,
        )

        config = resolver.resolve(
            self.arguments,
        )

        self.message.info(
            f"Dockerfiles configured: "
            f"{len(config.mappings)}",
        )

        executor = DockerFileFromImageChangeExecutor(
            filesystem=self.filesystem,
            message=self.message,
            log=self.log,
        )

        context = executor.execute(
            config,
        )

        self.outputs.update(
            context,
        )

        self.message.info(
            f"Dockerfiles changed: "
            f"{len(context['changes'])}",
        )

        self.message.info(
            f"Images requiring build: "
            f"{len(context['images'])}",
        )

        if context["build_required"]:

            self.message.info(
                "Image build is required.",
            )

        else:

            self.message.info(
                "No image build is required.",
            )

        return self._result(
            success=True,
            changed=bool(
                context["changes"],
            ),
        )

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def _result(
        self,
        *,
        success: bool,
        changed: bool,
        errors: list[str] | None = None,
    ) -> PluginResult:
        """
        Create the standard plugin result.
        """

        return PluginResult(
            success=success,
            changed=changed,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=errors or [],
            warnings=[],
            metadata={
                "artifacts": {
                    name: str(path)
                    for name, path
                    in self.artifacts.items()
                },
            },
        )
