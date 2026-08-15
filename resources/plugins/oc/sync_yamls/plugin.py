"""
OpenShift YAML synchronization plugin.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import SyncYamlsPluginException


class SyncYamlsPlugin(
    BasePlugin,
):
    """
    Synchronize OpenShift resources into a YAML repository.
    """

    DEFAULT_IGNORE_RESOURCES = {
        "configmaps": {
            "keys": [
                "kube.crt",
            ],
        },
    }

    RESOURCE_TYPES = (
        "deployments",
        "configmaps",
        "secrets",
        "services",
        "routes",
    )

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute YAML synchronization.
        """

        self.message.info(
            "Starting sync_yamls.",
        )

        try:

            with self.activity(
                "sync_yamls",
            ):

                return self._execute()

        except SyncYamlsPluginException as exc:

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

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:
        """
        Synchronize OpenShift resources.
        """

        api_url = self.arguments.string(
            "api_url",
        )

        namespace = self.arguments.string(
            "namespace",
        )

        username = self.arguments.string(
            "username",
        )

        password = self.arguments.string(
            "password",
        )

        yaml_repository = self.arguments.string(
            "yaml_repository",
        )

        ignore_resources = self.arguments.dictionary(
            "ignore_resources",
            {},
        )

        self._validate(
            api_url=api_url,
            namespace=namespace,
            username=username,
            password=password,
            yaml_repository=yaml_repository,
        )

        repository = Path(
            yaml_repository,
        )

        self._prepare_repository(
            repository,
        )

        kubeconfig = self._create_kubeconfig(
            repository=repository,
        )

        try:

            self._login(
                api_url=api_url,
                username=username,
                password=password,
                kubeconfig=kubeconfig,
            )

            resources = self._sync_resources(
                repository=repository,
                kubeconfig=kubeconfig,
                ignore_resources=ignore_resources,
            )

            deployment_index = self._create_deployment_index(
                repository=repository,
                resources=resources,
            )

            self.outputs.update(
                {
                    "repository": str(repository),
                    "namespace": namespace,
                    "resources": resources,
                    "deployment_index": str(
                        deployment_index,
                    ),
                },
            )

            return self._result(
                success=True,
                changed=True,
            )

        finally:

            self._logout(
                kubeconfig=kubeconfig,
            )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(
        *,
        api_url: str | None,
        namespace: str | None,
        username: str | None,
        password: str | None,
        yaml_repository: str | None,
    ) -> None:
        """
        Validate required plugin arguments.
        """

        required = {
            "api_url": api_url,
            "namespace": namespace,
            "username": username,
            "password": password,
            "yaml_repository": yaml_repository,
        }

        missing = [
            name
            for name, value in required.items()
            if value is None or not value.strip()
        ]

        if missing:

            raise SyncYamlsPluginException(
                "Missing required argument(s): "
                + ", ".join(missing),
            )

    # ------------------------------------------------------------------
    # Repository
    # ------------------------------------------------------------------

    def _prepare_repository(
        self,
        repository: Path,
    ) -> None:
        """
        Prepare the YAML repository directory.
        """

        try:

            self.filesystem.mkdir(
                repository,
                parents=True,
                exist_ok=True,
            )

        except (OSError, ValueError) as exc:

            raise SyncYamlsPluginException(
                f"Unable to create YAML repository "
                f"'{repository}': {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Kubeconfig
    # ------------------------------------------------------------------

    def _create_kubeconfig(
        self,
        *,
        repository: Path,
    ) -> Path:
        """
        Create an isolated kubeconfig for this plugin execution.
        """

        session_directory = (
            self.context.workspace
            / "session"
        )

        try:

            self.filesystem.mkdir(
                session_directory,
                parents=True,
                exist_ok=True,
            )

        except OSError as exc:

            raise SyncYamlsPluginException(
                f"Unable to create session directory "
                f"'{session_directory}': {exc}",
            ) from exc

        kubeconfig = (
            session_directory
            / "sync_yamls_kubeconfig"
        )

        return kubeconfig

    # ------------------------------------------------------------------
    # OpenShift login
    # ------------------------------------------------------------------

    def _login(
        self,
        *,
        api_url: str,
        username: str,
        password: str,
        kubeconfig: Path,
    ) -> None:
        """
        Login to OpenShift using an isolated kubeconfig.
        """

        self.message.info(
            f"Logging into OpenShift: {api_url}",
        )

        result = self._oc(
            [
                "login",
                api_url,
                f"--username={username}",
                f"--password={password}",
                "--insecure-skip-tls-verify",
            ],
            kubeconfig=kubeconfig,
        )

        if result.failed:

            message = result.stderr.strip()

            if not message:

                message = (
                    "OpenShift login failed "
                    f"with exit code {result.exit_code}."
                )

            raise SyncYamlsPluginException(
                message,
            )

    # ------------------------------------------------------------------
    # Resource synchronization
    # ------------------------------------------------------------------

    def _sync_resources(
        self,
        *,
        repository: Path,
        kubeconfig: Path,
        ignore_resources: dict[str, Any],
    ) -> dict[str, int]:
        """
        Synchronize supported OpenShift resources.
        """

        resources: dict[str, int] = {}

        for resource_type in self.RESOURCE_TYPES:

            self.message.info(
                f"Synchronizing {resource_type}.",
            )

            count = self._sync_resource_type(
                resource_type=resource_type,
                repository=repository,
                kubeconfig=kubeconfig,
                ignore_resources=ignore_resources,
            )

            resources[resource_type] = count

        return resources

    def _sync_resource_type(
        self,
        *,
        resource_type: str,
        repository: Path,
        kubeconfig: Path,
        ignore_resources: dict[str, Any],
    ) -> int:
        """
        Synchronize one OpenShift resource type.
        """

        result = self._oc(
            [
                "get",
                resource_type,
                "-o",
                "json",
            ],
            kubeconfig=kubeconfig,
        )

        if result.failed:

            raise SyncYamlsPluginException(
                f"Unable to retrieve {resource_type}: "
                f"{result.stderr.strip()}",
            )

        try:

            document = json.loads(
                result.stdout,
            )

        except json.JSONDecodeError as exc:

            raise SyncYamlsPluginException(
                f"Invalid JSON returned by OpenShift "
                f"for {resource_type}.",
            ) from exc

        items = document.get(
            "items",
            [],
        )

        if not isinstance(
            items,
            list,
        ):

            raise SyncYamlsPluginException(
                f"Invalid OpenShift response for "
                f"{resource_type}.",
            )

        target = repository / resource_type

        self._prepare_repository(
            target,
        )

        count = 0

        for item in items:

            if not isinstance(
                item,
                dict,
            ):

                continue

            metadata = item.get(
                "metadata",
                {},
            )

            if not isinstance(
                metadata,
                dict,
            ):

                continue

            name = metadata.get(
                "name",
            )

            if not isinstance(
                name,
                str,
            ) or not name:

                continue

            if self._ignored(
                resource_type,
                name,
                item,
                ignore_resources,
            ):

                self.log.info(
                    f"Ignoring {resource_type}/{name}.",
                )

                continue

            self._write_resource(
                target=target,
                name=name,
                resource=item,
            )

            count += 1

        return count

    # ------------------------------------------------------------------
    # Ignore
    # ------------------------------------------------------------------

    def _ignored(
        self,
        resource_type: str,
        name: str,
        resource: dict[str, Any],
        configured: dict[str, Any],
    ) -> bool:
        """
        Determine whether a resource should be ignored.
        """

        defaults = self.DEFAULT_IGNORE_RESOURCES.get(
            resource_type,
            {},
        )

        custom = configured.get(
            resource_type,
            {},
        )

        ignored_names = set(
            defaults.get(
                "names",
                [],
            )
            + custom.get(
                "names",
                [],
            ),
        )

        if name in ignored_names:

            return True

        if resource_type == "configmaps":

            data = resource.get(
                "data",
                {},
            )

            ignored_keys = set(
                defaults.get(
                    "keys",
                    [],
                )
                + custom.get(
                    "keys",
                    [],
                ),
            )

            if isinstance(data, dict):

                if any(
                    key in ignored_keys
                    for key in data
                ):

                    return True

        return False

    # ------------------------------------------------------------------
    # YAML
    # ------------------------------------------------------------------

    def _write_resource(
        self,
        *,
        target: Path,
        name: str,
        resource: dict[str, Any],
    ) -> None:
        """
        Write an OpenShift resource as YAML.
        """

        path = target / f"{name}.yaml"

        try:

            content = self.filesystem.dump_yaml(
                resource,
            )

            self.filesystem.write_text(
                path,
                content,
            )

        except (OSError, ValueError) as exc:

            raise SyncYamlsPluginException(
                f"Unable to write resource "
                f"'{path}': {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Deployment index
    # ------------------------------------------------------------------

    def _create_deployment_index(
        self,
        *,
        repository: Path,
        resources: dict[str, int],
    ) -> Path:
        """
        Create deployment_index.json.
        """

        entropy_directory = (
            repository / ".entropy"
        )

        self._prepare_repository(
            entropy_directory,
        )

        path = (
            entropy_directory
            / "deployment_index.json"
        )

        index = {
            "version": "1.0",
            "resources": resources,
        }

        try:

            self.filesystem.write_text(
                path,
                json.dumps(
                    index,
                    indent=4,
                ),
            )

        except OSError as exc:

            raise SyncYamlsPluginException(
                f"Unable to write deployment index "
                f"'{path}': {exc}",
            ) from exc

        return path

    # ------------------------------------------------------------------
    # OpenShift execution
    # ------------------------------------------------------------------

    def _oc(
        self,
        command: list[str],
        *,
        kubeconfig: Path,
    ):
        """
        Execute an OpenShift CLI command.
        """

        environment = {
            "KUBECONFIG": str(
                kubeconfig,
            ),
        }

        full_command = [
            "oc",
            *command,
        ]

        self.log.debug(
            f"Executing OpenShift command: "
            f"{' '.join(full_command)}",
        )

        try:

            result = self.shell.run(
                full_command,
                env=environment,
            )

        except FileNotFoundError as exc:

            raise SyncYamlsPluginException(
                "OpenShift CLI 'oc' was not found. "
                "Please install the OpenShift CLI and ensure "
                "it is available in PATH.",
            ) from exc

        except OSError as exc:

            raise SyncYamlsPluginException(
                f"Unable to execute OpenShift CLI: {exc}",
            ) from exc

        if result.stdout:

            self.log.info(
                f"OpenShift stdout:\n"
                f"{result.stdout.rstrip()}",
            )

        if result.stderr:

            self.log.warning(
                f"OpenShift stderr:\n"
                f"{result.stderr.rstrip()}",
            )

        self.outputs["exit_code"] = result.exit_code
        self.outputs["success"] = result.success
        self.outputs["stdout"] = result.stdout
        self.outputs["stderr"] = result.stderr
        self.outputs["duration"] = result.duration

        return result

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def _logout(
        self,
        *,
        kubeconfig: Path,
    ) -> None:
        """
        Remove the isolated kubeconfig.
        """

        try:

            if self.filesystem.exists(
                kubeconfig,
            ):

                self.filesystem.remove(
                    kubeconfig,
                )

        except OSError as exc:

            self.log.warning(
                f"Unable to remove kubeconfig "
                f"'{kubeconfig}': {exc}",
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
        Build the standard plugin result.
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
