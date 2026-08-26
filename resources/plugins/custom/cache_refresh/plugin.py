"""
Cache refresh plugin.
"""

from __future__ import annotations

from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import CacheRefreshPluginException
from .model import CacheRefreshConfig
from .resolver import CacheRefreshResolver


class CacheRefreshPlugin(BasePlugin):
    """
    OpenShift cache refresh and service restart plugin.
    """

    def execute(self) -> PluginResult:
        """
        Execute cache refresh operations.
        """

        self.message.info(
            "Starting cache_refresh.",
        )

        try:

            with self.activity(
                "cache_refresh",
            ):
                config = CacheRefreshResolver().resolve(
                    self.arguments,
                )

                self._verify_access(
                    config,
                )

                self.outputs.update(
                    {
                        "rebuild": config.rebuild,
                        "stop_all_before_cache_rebuild": (
                            config.stop_all_before_cache_rebuild
                        ),
                        "mode": config.mode,
                        "services": list(
                            config.services,
                        ),
                        "parallel": config.parallel,
                        "namespace": config.namespace,
                    },
                )

        except CacheRefreshPluginException as exc:

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
            "cache_refresh configuration validated successfully.",
        )

        return self._result(
            success=True,
            changed=False,
        )

    # ------------------------------------------------------------------
    # OpenShift
    # ------------------------------------------------------------------

    def _oc(
        self,
        command: list[str],
        *,
        config: CacheRefreshConfig,
    ) -> Any:
        """
        Execute an OpenShift command using the supplied kubeconfig.
        """

        full_command = [
            "oc",
            *command,
        ]

        self.log.debug(
            "Executing OpenShift command: "
            + " ".join(full_command),
        )

        try:

            result = self.shell.run(
                full_command,
                env={
                    "KUBECONFIG": str(
                        config.kubeconfig,
                    ),
                },
            )

        except FileNotFoundError as exc:

            raise CacheRefreshPluginException(
                "OpenShift CLI 'oc' was not found. "
                "Please install the OpenShift CLI and ensure "
                "it is available in PATH.",
            ) from exc

        except OSError as exc:

            raise CacheRefreshPluginException(
                f"Unable to execute OpenShift CLI: {exc}",
            ) from exc

        return result

    def _verify_access(
        self,
        config: CacheRefreshConfig,
    ) -> None:
        """
        Verify OpenShift authentication and required permissions.
        """

        result = self._oc(
            [
                "whoami",
            ],
            config=config,
        )

        if result.failed:

            message = result.stderr.strip()

            if not message:
                message = (
                    "OpenShift authentication is not available. "
                    "Please login using 'oc login' before running "
                    "cache_refresh."
                )

            raise CacheRefreshPluginException(
                message,
            )

        username = result.stdout.strip()

        if not username:
            raise CacheRefreshPluginException(
                "Unable to determine the current OpenShift user.",
            )

        self.message.info(
            f"OpenShift user: {username}",
        )

        self._verify_namespace(
            config,
        )

        self._verify_permissions(
            config,
        )

    def _verify_namespace(
        self,
        config: CacheRefreshConfig,
    ) -> None:
        """
        Verify access to the target namespace.
        """

        result = self._oc(
            [
                "auth",
                "can-i",
                "get",
                "deployments",
                "-n",
                config.namespace,
            ],
            config=config,
        )

        if result.failed:

            message = result.stderr.strip()

            if not message:
                message = (
                    f"Unable to verify access to namespace "
                    f"'{config.namespace}'."
                )

            raise CacheRefreshPluginException(
                message,
            )

        if result.stdout.strip().casefold() != "yes":

            raise CacheRefreshPluginException(
                "Current OpenShift user does not have "
                f"permission to access deployments in "
                f"namespace '{config.namespace}'.",
            )

    def _verify_permissions(
        self,
        config: CacheRefreshConfig,
    ) -> None:
        """
        Verify permissions required by the plugin.
        """

        permissions = [
            (
                "get",
                "deployments",
            ),
            (
                "update",
                "deployments",
            ),
            (
                "patch",
                "deployments",
            ),
            (
                "get",
                "pods",
            ),
            (
                "get",
                "pods/log",
            ),
        ]

        for verb, resource in permissions:

            result = self._oc(
                [
                    "auth",
                    "can-i",
                    verb,
                    resource,
                    "-n",
                    config.namespace,
                ],
                config=config,
            )

            if result.failed:

                message = result.stderr.strip()

                if not message:
                    message = (
                        f"Unable to verify permission "
                        f"'{verb}' on '{resource}'."
                    )

                raise CacheRefreshPluginException(
                    message,
                )

            if result.stdout.strip().casefold() != "yes":

                raise CacheRefreshPluginException(
                    "Current OpenShift user does not have "
                    f"permission to '{verb}' '{resource}' "
                    f"in namespace '{config.namespace}'.",
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
        Build plugin result.
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
                    for name, path in self.artifacts.items()
                },
            },
        )
