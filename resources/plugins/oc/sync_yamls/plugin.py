"""
OpenShift YAML synchronization plugin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import SyncYamlsPluginException


class SyncYamlsPlugin(BasePlugin):
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

    IGNORE_RESOURCE_FIELDS = (
        "names",
        "keys",
    )

    INDEX_DIRECTORY = ".entropy"

    INDEX_FILENAME = "deployment_index.json"

    STRUCTURE_FILENAME = "openshift.yaml"

    def execute(self) -> PluginResult:
        """
        Execute YAML synchronization.
        """

        self.message.info(
            "Starting sync_yamls.",
        )

        try:
            with self.activity("sync_yamls"):
                result = self._execute()

        except SyncYamlsPluginException as exc:
            self.log.error(str(exc))
            self.message.error(str(exc))

            return self._result(
                success=False,
                changed=bool(self.artifacts),
                errors=[str(exc)],
            )

        self.message.success(
            "sync_yamls completed successfully.",
        )

        return result

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(self) -> PluginResult:
        """
        Synchronize OpenShift resources and build the deployment index.
        """

        deployment_index: dict[str, Any] = {}

        arguments = self._arguments()

        self._validate(arguments)

        repository = self.filesystem.path(
            arguments["yaml_repository"],
        )

        self._prepare_repository(repository)

        structure = self._load_structure()

        self._verify_access(
            arguments["namespace"],
            kubeconfig=arguments["kubeconfig"],
        )

        resources = self._sync_resources(
            repository=repository,
            namespace=arguments["namespace"],
            structure=structure,
            ignore_resources=arguments["ignore_resources"],
            deployment_index=deployment_index,
            kubeconfig=arguments["kubeconfig"],
        )

        index_path = self._create_deployment_index(
            repository=repository,
            deployment_index=deployment_index,
        )

        self.outputs.update(
            {
                "repository": str(repository),
                "namespace": arguments["namespace"],
                "resources": resources,
                "deployment_index": str(index_path),
            },
        )

        return self._result(
            success=True,
            changed=True,
        )

    # ------------------------------------------------------------------
    # Arguments
    # ------------------------------------------------------------------

    def _arguments(self) -> dict[str, Any]:
        """
        Resolve plugin arguments.
        """

        ignore_resources = self.arguments.dictionary(
            "ignore_resources",
            {},
        )

        return {
            "kubeconfig": self.arguments.path(
                "kubeconfig",
                required=True,
            ),
            "namespace": self.arguments.string(
                "namespace",
                 required=True,
            ),
            "yaml_repository": self.arguments.string(
                "yaml_repository",
                 required=True,
            ),
            "ignore_resources": self._normalize_ignore_resources(
                ignore_resources,
            ),
        }

    @classmethod
    def _normalize_ignore_resources(
        cls,
        configured: dict[str, Any],
    ) -> dict[str, dict[str, list[str]]]:
        """
        Validate and normalize ignore-resource configuration.

        Only supported resource types and fields are accepted.
        Missing values are populated from the defaults.
        """

        if not isinstance(configured, dict):
            raise SyncYamlsPluginException(
                "'ignore_resources' must be a dictionary.",
            )

        normalized: dict[str, dict[str, list[str]]] = {}

        for resource_type, defaults in cls.DEFAULT_IGNORE_RESOURCES.items():
            custom = configured.get(
                resource_type,
                {},
            )

            if custom is None:
                custom = {}

            if not isinstance(custom, dict):
                raise SyncYamlsPluginException(
                    f"'ignore_resources.{resource_type}' "
                    "must be a dictionary.",
                )

            resource_config: dict[str, list[str]] = {}

            for field in cls.IGNORE_RESOURCE_FIELDS:
                default_values = defaults.get(
                    field,
                    [],
                )

                custom_values = custom.get(
                    field,
                    [],
                )

                if not isinstance(custom_values, list):
                    raise SyncYamlsPluginException(
                        f"'ignore_resources.{resource_type}.{field}' "
                        "must be a list.",
                    )

                if not all(
                    isinstance(value, str)
                    for value in custom_values
                ):
                    raise SyncYamlsPluginException(
                        f"All values in "
                        f"'ignore_resources.{resource_type}.{field}' "
                        "must be strings.",
                    )

                resource_config[field] = list(
                    dict.fromkeys(
                        [
                            *default_values,
                            *custom_values,
                        ],
                    ),
                )

            normalized[resource_type] = resource_config

        unsupported = set(configured).difference(
            cls.DEFAULT_IGNORE_RESOURCES,
        )

        if unsupported:
            raise SyncYamlsPluginException(
                "Unsupported ignore resource type(s): "
                + ", ".join(
                    sorted(unsupported),
                ),
            )

        return normalized

    @staticmethod
    def _validate(
        arguments: dict[str, Any],
    ) -> None:
        """
        Validate required plugin arguments.
        """

        required = (
            "namespace",
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
                + ", ".join(missing),
            )

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------

    def _load_structure(self) -> dict[str, Any]:
        """
        Load the OpenShift normalization structure.
        """

        structure_path = (
            self.structures
            / self.STRUCTURE_FILENAME
        )

        try:
            structure = self.normalizer.load_structure(
                structure_path,
            )
        except (OSError, ValueError, TypeError) as exc:
            raise SyncYamlsPluginException(
                "Unable to load OpenShift structure "
                f"'{structure_path}': {exc}",
            ) from exc

        if not isinstance(structure, dict):
            raise SyncYamlsPluginException(
                f"Invalid OpenShift structure "
                f"'{structure_path}'.",
            )

        return structure

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
    # OpenShift
    # ------------------------------------------------------------------

    def _oc(
        self,
        command: list[str],
        *,
        kubeconfig: Path,
    ) -> Any:
        """
        Execute an OpenShift CLI command using the current
        authenticated OpenShift context.
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
                env = {
                    "KUBECONFIG" : str(kubeconfig)
                }
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

        stderr = result.stderr.strip()

        if stderr:
            self.log.warning(
                "OpenShift stderr:\n"
                + stderr,
            )

        return result

    def _verify_access(
        self,
        namespace: str,
        kubeconfig: Path,
    ) -> None:
        """
        Verify that the current OpenShift session is authenticated
        and can access the target namespace and resources.
        """

        result = self._oc(
            [
                "whoami",
            ],
            kubeconfig=kubeconfig,
        )

        if result.failed:
            message = result.stderr.strip()

            if not message:
                message = (
                    "OpenShift authentication is not available. "
                    "Please login using 'oc login' before running "
                    "sync_yamls."
                )

            raise SyncYamlsPluginException(message)

        username = result.stdout.strip()

        if not username:
            raise SyncYamlsPluginException(
                "Unable to determine the current OpenShift user.",
            )

        self.message.info(
            f"OpenShift user: {username}",
        )

        self._verify_namespace_access(
            namespace=namespace,
            kubeconfig=kubeconfig,
        )

    def _verify_namespace_access(
        self,
        namespace: str,
        kubeconfig: Path,
    ) -> None:
        """
        Verify that the current user can read all resources required
        by the synchronization.
        """

        self.message.info(
            f"Verifying access to namespace '{namespace}'...",
        )

        for resource_type in self.RESOURCE_TYPES:
            result = self._oc(
                [
                    "auth",
                    "can-i",
                    "get",
                    resource_type,
                    "-n",
                    namespace,
                ],
                kubeconfig=kubeconfig,
            )

            if result.failed:
                message = result.stderr.strip()

                if not message:
                    message = (
                        f"Unable to verify access to "
                        f"{resource_type} in namespace "
                        f"'{namespace}'."
                    )

                raise SyncYamlsPluginException(message)

            if result.stdout.strip().casefold() != "yes":
                raise SyncYamlsPluginException(
                    f"Current OpenShift user does not have permission "
                    f"to get {resource_type} in namespace "
                    f"'{namespace}'.",
                )

    # ------------------------------------------------------------------
    # Synchronization
    # ------------------------------------------------------------------

    def _sync_resources(
        self,
        *,
        repository: Path,
        namespace: str,
        structure: dict[str, Any],
        ignore_resources: dict[str, dict[str, list[str]]],
        deployment_index: dict[str, Any],
        kubeconfig: Path,
    ) -> dict[str, list[str]]:
        """
        Synchronize all supported resource categories.
        """

        resources: dict[str, list[str]] = {}

        for resource_type in self.RESOURCE_TYPES:
            resources[resource_type] = self._sync_resource_type(
                resource_type=resource_type,
                repository=repository,
                namespace=namespace,
                structure=structure,
                ignore_resources=ignore_resources,
                deployment_index=deployment_index,
                kubeconfig=kubeconfig,
            )

        return resources

    def _sync_resource_type(
        self,
        *,
        resource_type: str,
        repository: Path,
        namespace: str,
        structure: dict[str, Any],
        ignore_resources: dict[str, dict[str, list[str]]],
        deployment_index: dict[str, Any],
        kubeconfig: Path,
    ) -> list[str]:
        """
        Synchronize one OpenShift resource category.
        """

        with self.activity(resource_type):
            result = self._oc(
                [
                    "get",
                    resource_type,
                    "-n",
                    namespace,
                    "-o",
                    "json",
                ],
                kubeconfig=kubeconfig
            )

            if result.failed:
                message = result.stderr.strip()

                if not message:
                    message = (
                        f"Unable to retrieve {resource_type} "
                        f"from namespace '{namespace}'."
                    )

                raise SyncYamlsPluginException(message)

            try:
                document = self.filesystem.parse_json(
                    result.stdout,
                )
            except ValueError as exc:
                raise SyncYamlsPluginException(
                    "Invalid JSON returned by OpenShift "
                    f"for {resource_type}.",
                ) from exc

            if not isinstance(document, dict):
                raise SyncYamlsPluginException(
                    f"Invalid OpenShift response for "
                    f"{resource_type}: expected an object.",
                )

            items = document.get(
                "items",
                [],
            )

            if not isinstance(items, list):
                raise SyncYamlsPluginException(
                    f"Invalid OpenShift response for "
                    f"{resource_type}: 'items' must be a list.",
                )

            if not items:
                self.message.info(
                    f"No {resource_type} found.",
                )
                return []

            target = repository / resource_type

            self._prepare_repository(target)

            self.message.info(
                f"Processing {len(items)} "
                f"{resource_type}.",
            )

            files: list[str] = []

            for item in items:
                if not isinstance(item, dict):
                    self.log.warning(
                        f"Skipping invalid {resource_type} item.",
                    )
                    continue

                metadata = item.get(
                    "metadata",
                    {},
                )

                if not isinstance(metadata, dict):
                    self.log.warning(
                        f"Skipping {resource_type} with invalid "
                        "metadata.",
                    )
                    continue

                name = metadata.get("name")

                if not isinstance(name, str) or not name.strip():
                    self.log.warning(
                        f"Skipping {resource_type} without a valid name.",
                    )
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
                    deployment_index[relative] = (
                        self._deployment_index_entry(
                            resource,
                        )
                    )

                files.append(relative)
                self.artifacts[relative] = path

                self.message.success(
                    Path(relative).name,
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
        ignore_resources: dict[str, dict[str, list[str]]],
    ) -> dict[str, Any]:
        """
        Normalize and clean one OpenShift resource.
        """

        try:
            normalized = self.normalizer.normalize(
                resource,
                structure,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise SyncYamlsPluginException(
                f"Unable to normalize {resource_type} "
                f"'{self._resource_name(resource)}': {exc}",
            ) from exc

        if not isinstance(normalized, dict):
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

    @staticmethod
    def _resource_name(
        resource: dict[str, Any],
    ) -> str:
        """
        Return a resource name for error messages.
        """

        metadata = resource.get(
            "metadata",
            {},
        )

        if isinstance(metadata, dict):
            name = metadata.get("name")

            if isinstance(name, str) and name.strip():
                return name

        return "<unknown>"

    def _remove_ignored_keys(
        self,
        *,
        resource_type: str,
        resource: dict[str, Any],
        configured: dict[str, dict[str, list[str]]],
    ) -> None:
        """
        Remove configured data keys from ConfigMaps and Secrets.
        """

        if resource_type not in (
            "configmaps",
            "secrets",
        ):
            return

        data = resource.get("data")

        if not isinstance(data, dict):
            return

        resource_config = configured.get(
            resource_type,
            {},
        )

        ignored_keys = resource_config.get(
            "keys",
            [],
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
        configured: dict[str, dict[str, list[str]]],
    ) -> bool:
        """
        Determine whether an entire resource should be ignored.
        """

        resource_config = configured.get(
            resource_type,
            {},
        )

        names = resource_config.get(
            "names",
            [],
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

        path = target / f"{name}.yaml"

        try:
            self.filesystem.write_yaml(
                path,
                resource,
            )
        except (OSError, ValueError, TypeError) as exc:
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

        directory = repository / self.INDEX_DIRECTORY

        self._prepare_repository(directory)

        path = directory / self.INDEX_FILENAME

        try:
            self.filesystem.write_json(
                path,
                deployment_index,
            )
        except (OSError, ValueError, TypeError) as exc:
            raise SyncYamlsPluginException(
                f"Unable to write deployment index "
                f"'{path}': {exc}",
            ) from exc

        relative = self._relative_path(
            repository,
            path,
        )

        self.artifacts[relative] = path

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
            path.relative_to(repository),
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
            outputs=dict(self.outputs),
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

        if not isinstance(deployment_name, str):
            deployment_name = ""

        result: dict[str, Any] = {
            "deployment": deployment_name,
            "containers": {},
        }

        if not isinstance(containers, list):
            return result

        for container in containers:
            if not isinstance(container, dict):
                continue

            name = container.get("name")
            image = container.get("image")

            if not isinstance(name, str) or not name.strip():
                continue

            if not isinstance(image, str) or not image.strip():
                continue

            result["containers"][name] = {
                "image": image,
            }

        return result
