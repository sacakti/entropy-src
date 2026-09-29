"""
Release context builder plugin.
"""

from __future__ import annotations

from pathlib import Path

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .analyzer import ReleaseAnalyzer
from .exceptions import ContextBuilderPluginException


class ContextBuilderPlugin(
    BasePlugin,
):
    """
    Analyse a release and produce deployment context.
    """

    def execute(
        self,
    ) -> PluginResult:
        """
        Build the release execution context.
        """

        self.message.info(
            "Starting release context analysis.",
        )

        try:

            with self.activity(
                "release-context-builder",
            ):

                result = self._execute()

        except ContextBuilderPluginException as exc:

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
            "Release context analysis completed successfully.",
        )

        return result

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:
        """
        Resolve typed arguments and analyse the release.
        """

        release = self.arguments.path(
            "release",
            required=True,
        )

        docker_repository = self.arguments.path(
            "docker_repository",
            required=True,
        )

        yaml_repository = self.arguments.path(
            "yaml_repository",
            required=True,
        )

        image_tag = self.arguments.string(
            "image_tag",
            required=True,
        )

        structure = self.arguments.path(
            "structure",
        )

        if structure is None:

            structure = Path(__file__).resolve().parent / "structure.yaml"

        assert release is not None
        assert docker_repository is not None
        assert yaml_repository is not None
        assert image_tag is not None

        analyzer = ReleaseAnalyzer(
            filesystem=self.filesystem,
            archive=self.archive,
            message=self.message,
            log=self.log,
            activity=self.activity,
        )

        context = analyzer.analyze(
            release=release,
            docker_repository=docker_repository,
            yaml_repository=yaml_repository,
            image_tag=image_tag,
            structure=structure,
        )

        context["workspace"] = str(self.workspace)

        self.outputs.update(
            context,
        )

        self.message.info(
            f"Images requiring build: " f"{len(context['images'])}",
        )

        deployment = context["deployment"]

        self.message.info(
            f"Deployment changes: " f"{self._deployment_count(deployment)}",
        )

        self.message.info(
            f"Database scripts discovered: " f"{len(context['database']['scripts'])}",
        )

        self.message.info(
            f"Rsync operations: " f"{len(context['common_paths'])}",
        )

        return self._result(
            success=True,
            changed=True,
        )

    # ------------------------------------------------------------------
    # Deployment
    # ------------------------------------------------------------------

    @staticmethod
    def _deployment_count(
        deployment,
    ) -> int:
        """
        Count planned deployment resource changes.
        """

        resources = deployment.get(
            "resources",
            {},
        )

        return sum(len(value) for value in resources.values())

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
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )
