"""
OpenShift YAML synchronization plugin.
"""

from __future__ import annotations

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
            "names": [],
            "keys": [
                "kube.crt",
            ],
        },
        "secrets": {
            "names": [],
            "keys": [],
        },
    }

    RESOURCE_TYPES = (
        "deployments",
        "configmaps",
        "secrets",
        "services",
        "routes",
    )

    INDEX_DIRECTORY = ".entropy"

    INDEX_FILENAME = "deployment_index.json"

    STRUCTURE_FILENAME = "openshift.yaml"

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

                result = self._execute()

        except SyncYamlsPluginException as exc:

            self.log.error(
                str(exc),
            )

            self.message.error(
                str(exc),
            )

            return self._result(
                success=False,
                changed=bool(
                    self.artifacts,
                ),
                errors=[
                    str(exc),
                ],
            )

        self.message.success(
            "sync_yamls completed successfully.",
        )

        return result

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:
        """
        Synchronize OpenShift resources and build the deployment index.
        """

        deployment_index: dict[str, Any] = {}

        arguments = self._arguments()

        self._validate(
            arguments,
        )

        repository = self.filesystem.path(
            arguments["yaml_repository"],
        )

        self._prepare_repository(
            repository,
        )

        structure = self._load_structure()

        kubeconfig = self._create_kubeconfig()

        try:

            self._login(
                api_url=arguments["api_url"],
                username=arguments["username"],
                password=arguments["password"],
                kubeconfig=kubeconfig,
            )

            resources = self._sync_resources(
                repository=repository,
                kubeconfig=kubeconfig,
                structure=structure,
                ignore_resources=arguments[
                    "ignore_resources"
                ],
                deployment_index=deployment_index,
            )

            index_path = self._create_deployment_index(
                repository=repository,
                deployment_index=deployment_index,
            )

            self.outputs.update(
                {
                    "repository": str(
                        repository,
                    ),
                    "namespace": arguments[
                        "namespace"
                    ],
                    "resources": resources,
                    "deployment_index": str(
                        index_path,
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
    # Arguments
    # ------------------------------------------------------------------

    def _arguments(
        self,
    ) -> dict[str, Any]:
        """
        Resolve plugin arguments.
        """

        ignore_resources = self.arguments.dictionary(
            "ignore_resources",
            {},
        )

        return {
            "api_url": self.arguments.string(
                "api_url",
            ),
            "namespace": self.arguments.string(
                "namespace",
            ),
            "username": self.arguments.string(
                "username",
            ),
            "password": self.arguments.string(
                "password",
            ),
            "yaml_repository": self.arguments.string(
                "yaml_repository",
            ),
            "ignore_resources": ignore_resources,
        }

    @staticmethod
    def _validate(
        arguments: dict[str, Any],
    ) -> None:
        """
        Validate required plugin arguments.
        """

        required = (
            "api_url",
            "namespace",
            "username",
            "password",
            "yaml_repository",
        )

        missing = [
            name
            for name in required
            if not isinstance(
                arguments.get(name),
                str,
            )
            or not arguments[name].strip()
        ]

        if missing:

            raise SyncYamlsPluginException(
                "Missing required argument(s): "
                + ", ".join(
                    missing,
                ),
            )

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------

    def _load_structure(
        self,
    ) -> dict[str, Any]:
        """
        Load the OpenShift normalization structure.
        """

        structure_path = (
            self.structures
            / self.STRUCTURE_FILENAME
        )

        try:

            return self.normalizer.load_structure(
                structure_path,
            )

        except Exception as exc:

            raise SyncYamlsPluginException(
                "Unable to load OpenShift structure "
                f"'{structure_path}': {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Repository
    # ------------------------------------------------------------------

    def _prepare_repository(
        self,
        repository: Path,
    ) -> None:
        """
        Prepare a repository directory.
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
    ) -> Path:
        """
        Create an isolated kubeconfig for this execution.
        """

        directory = (
            self.session_directory
            / "sync_yamls"
        )

        try:

            self.filesystem.mkdir(
                directory,
                parents=True,
                exist_ok=True,
            )

        except (OSError, ValueError) as exc:

            raise SyncYamlsPluginException(
                "Unable to create OpenShift session "
                f"directory '{directory}': {exc}",
            ) from exc

        return (
            directory
            / "kubeconfig"
        )

    # ------------------------------------------------------------------
    # OpenShift
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

    def _logout(
        self,
        *,
        kubeconfig: Path,
    ) -> None:
        """
        Remove the isolated kubeconfig.
        """

        if not self.filesystem.exists(
            kubeconfig,
        ):

            return

        try:

            self.filesystem.remove(
                kubeconfig,
            )

        except OSError as exc:

            self.log.warning(
                "Unable to remove OpenShift kubeconfig "
                f"'{kubeconfig}': {exc}",
            )

    def _oc(
        self,
        command: list[str],
        *,
        kubeconfig: Path,
    ):
        """
        Execute an OpenShift CLI command using the
        isolated kubeconfig.
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
            "Executing OpenShift command: "
            + " ".join(
                full_command,
            ),
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

        if result.stderr:

            self.log.warning(
                f"OpenShift stderr:\n"
                f"{result.stderr.rstrip()}",
            )

        return result

    # ------------------------------------------------------------------
    # Synchronization
    # ------------------------------------------------------------------

    def _sync_resources(
        self,
        *,
        repository: Path,
        kubeconfig: Path,
        structure: dict[str, Any],
        ignore_resources: dict[str, Any],
        deployment_index: dict[str, Any],
    ) -> dict[str, list[str]]:
        """
        Synchronize all supported resource categories.
        """

        resources: dict[str, list[str]] = {}

        for resource_type in self.RESOURCE_TYPES:

            resources[resource_type] = (
                self._sync_resource_type(
                    resource_type=resource_type,
                    repository=repository,
                    kubeconfig=kubeconfig,
                    structure=structure,
                    ignore_resources=ignore_resources,
                    deployment_index=deployment_index,
                )
            )

        return resources

    def _sync_resource_type(
        self,
        *,
        resource_type: str,
        repository: Path,
        kubeconfig: Path,
        structure: dict[str, Any],
        ignore_resources: dict[str, Any],
        deployment_index: dict[str, Any],
    ) -> list[str]:
        """
        Synchronize one OpenShift resource category.
        """

        with self.activity(
            resource_type,
        ):

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

                document = self.filesystem.parse_json(
                    result.stdout,
                )

            except ValueError as exc:

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

            if not items:

                self.message.info(
                    f"No {resource_type} found.",
                )

                return []

            target = (
                repository
                / resource_type
            )

            self._prepare_repository(
                target,
            )

            self.message.info(
                f"Processing {len(items)} "
                f"{resource_type}.",
            )

            files: list[str] = []

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
                ) or not name.strip():

                    continue

                if self._ignored(
                    resource_type=resource_type,
                    name=name,
                    configured=ignore_resources,
                ):

                    self.log.info(
                        f"Ignoring {resource_type}/{name}.",
                    )

                    continue

                self.message.info(
                    f"Downloading "
                    f"{self._resource_label(resource_type)} "
                    f"'{name}'...",
                )

                resource = self._normalize_resource(
                    resource_type=resource_type,
                    resource=item,
                    structure=structure,
                    ignore_resources=ignore_resources,
                )

                path = self._write_resource(
                    target=target,
                    name=name,
                    resource=resource,
                )

                relative = self._relative_path(
                    repository,
                    path,
                )

                if resource_type == "deployments":

                    deployment_index[
                        relative
                    ] = self._deployment_index_entry(
                        resource,
                    )

                files.append(
                    relative,
                )

                self.artifacts[
                    relative
                ] = path

                self.message.success(
                    f"{Path(relative).name}",
                )

            self.message.success(
                f"{resource_type.capitalize()} completed. "
                f"{len(files)} file(s).",
            )

            return files

    # ------------------------------------------------------------------
    # Resource normalization
    # ------------------------------------------------------------------

    def _normalize_resource(
        self,
        *,
        resource_type: str,
        resource: dict[str, Any],
        structure: dict[str, Any],
        ignore_resources: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Normalize and clean one OpenShift resource.
        """

        normalized = self.normalizer.normalize(
            resource,
            structure,
        )

        if not isinstance(
            normalized,
            dict,
        ):

            raise SyncYamlsPluginException(
                "OpenShift normalizer returned an invalid "
                f"document for {resource_type}.",
            )

        self._remove_ignored_keys(
            resource_type=resource_type,
            resource=normalized,
            configured=ignore_resources,
        )

        return normalized

    def _remove_ignored_keys(
        self,
        *,
        resource_type: str,
        resource: dict[str, Any],
        configured: dict[str, Any],
    ) -> None:
        """
        Remove configured data keys from a resource.
        """

        if resource_type != "configmaps":

            return

        data = resource.get(
            "data",
        )

        if not isinstance(
            data,
            dict,
        ):

            return

        defaults = self.DEFAULT_IGNORE_RESOURCES.get(
            resource_type,
            {},
        )

        custom = configured.get(
            resource_type,
            {},
        )

        if not isinstance(
            custom,
            dict,
        ):

            custom = {}

        ignored_keys = set(
            defaults.get(
                "keys",
                [],
            ),
        )

        ignored_keys.update(
            custom.get(
                "keys",
                [],
            ),
        )

        for key in ignored_keys:

            data.pop(
                key,
                None,
            )

    # ------------------------------------------------------------------
    # Ignore
    # ------------------------------------------------------------------

    def _ignored(
        self,
        *,
        resource_type: str,
        name: str,
        configured: dict[str, Any],
    ) -> bool:
        """
        Determine whether an entire resource should be ignored.
        """

        defaults = self.DEFAULT_IGNORE_RESOURCES.get(
            resource_type,
            {},
        )

        custom = configured.get(
            resource_type,
            {},
        )

        if not isinstance(
            custom,
            dict,
        ):

            custom = {}

        names = set(
            defaults.get(
                "names",
                [],
            ),
        )

        names.update(
            custom.get(
                "names",
                [],
            ),
        )

        return name in names

    # ------------------------------------------------------------------
    # File writing
    # ------------------------------------------------------------------

    def _write_resource(
        self,
        *,
        target: Path,
        name: str,
        resource: dict[str, Any],
    ) -> Path:
        """
        Format and write one resource YAML.
        """

        path = (
            target
            / f"{name}.yaml"
        )

        try:

            self.filesystem.write_yaml(
                path,
                resource,
            )

        except (OSError, ValueError) as exc:

            raise SyncYamlsPluginException(
                f"Unable to write resource "
                f"'{path}': {exc}",
            ) from exc

        return path

    # ------------------------------------------------------------------
    # Deployment index
    # ------------------------------------------------------------------

    def _create_deployment_index(
        self,
        *,
        repository: Path,
        deployment_index: dict[str, Any],
    ) -> Path:
        """
        Create deployment_index.json.
        """

        directory = (
            repository
            / self.INDEX_DIRECTORY
        )

        self._prepare_repository(
            directory,
        )

        path = (
            directory
            / self.INDEX_FILENAME
        )

        try:

            self.filesystem.write_json(
                path,
                deployment_index,
            )

        except (OSError, ValueError) as exc:

            raise SyncYamlsPluginException(
                f"Unable to write deployment index "
                f"'{path}': {exc}",
            ) from exc

        self.artifacts[
            self.INDEX_FILENAME
        ] = path

        return path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resource_label(
        resource_type: str,
    ) -> str:
        """
        Return a human-readable resource type.
        """

        return resource_type[:-1]

    @staticmethod
    def _relative_path(
        repository: Path,
        path: Path,
    ) -> str:
        """
        Return a repository-relative path.
        """

        return str(
            path.relative_to(
                repository,
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
        Build the plugin result.
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

    def _deployment_index_entry(
        self,
        deployment: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build a deployment index entry.
        """

        metadata = deployment.get(
            "metadata",
            {},
        )

        spec = deployment.get(
            "spec",
            {},
        )

        template = (
            spec.get(
                "template",
                {},
            )
            if isinstance(spec, dict)
            else {}
        )

        pod_spec = (
            template.get(
                "spec",
                {},
            )
            if isinstance(template, dict)
            else {}
        )

        containers = (
            pod_spec.get(
                "containers",
                [],
            )
            if isinstance(pod_spec, dict)
            else []
        )

        deployment_name = (
            metadata.get(
                "name",
            )
            if isinstance(metadata, dict)
            else None
        )

        if not isinstance(
            deployment_name,
            str,
        ):
            deployment_name = ""

        result: dict[str, Any] = {
            "deployment": deployment_name,
            "containers": {},
        }

        if not isinstance(
            containers,
            list,
        ):
            return result

        for container in containers:

            if not isinstance(
                container,
                dict,
            ):
                continue

            name = container.get(
                "name",
            )

            image = container.get(
                "image",
            )

            if not isinstance(
                name,
                str,
            ) or not name.strip():

                continue

            if not isinstance(
                image,
                str,
            ) or not image.strip():

                continue

            result["containers"][name] = {
                "image": image,
            }

        return result
