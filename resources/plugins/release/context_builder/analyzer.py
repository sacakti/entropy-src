"""
Release package analyser.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from .detector import ReleaseChangeDetector
from .exceptions import ContextBuilderPluginException
from .resource_index import ResourceIndex
from .structure import ReleaseStructureResolver


class ReleaseAnalyzer:
    """
    Analyse a release using a configurable release structure.
    """

    YAML_EXTENSIONS = {
        ".yaml",
        ".yml",
    }

    PLAN_EXTENSIONS = {
        ".yaml",
        ".yml",
        ".json",
    }

    SHELL_SEPARATORS = {
        "&&",
        "||",
        ";",
        "|",
        "&",
    }

    # docker push options that take a separate value argument.
    DOCKER_PUSH_VALUE_OPTIONS = {
        "--platform",
    }

    def __init__(
        self,
        *,
        filesystem,
        archive,
        message,
        log,
        activity,
    ) -> None:

        self._filesystem = filesystem
        self._archive = archive
        self._message = message
        self._log = log
        self._activity = activity

        self._changes = ReleaseChangeDetector(
            filesystem,
        )

        self._structures = ReleaseStructureResolver(
            filesystem,
        )

        self._resource_index = ResourceIndex(
            filesystem=filesystem,
            log=log,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def analyze(
        self,
        *,
        release: Path,
        docker_repository: Path,
        yaml_repository: Path,
        image_tag: str,
        structure: Path,
        image_transfer_script: str = "scripts/deploy/image_transfer.sh",
    ) -> dict[str, Any]:

        release = release.expanduser().resolve()
        structure = structure.expanduser().resolve()

        self._validate_release(
            release,
        )

        definition = self._structures.load(
            structure,
        )

        release_root = self._extract(
            release,
        )

        release_root = self._structures.find_root(
            release_root,
            definition,
        )

        if release_root is None:

            raise ContextBuilderPluginException(
                "Unable to locate the release root matching " "the configured release structure.",
            )

        resource_index = self._resource_index.load(
            yaml_repository,
        )

        docker_definition = definition.component(
            "docker",
        )

        if docker_definition is not None:

            docker_source_release = self._structures.path(
                release_root,
                docker_definition,
            )

        else:

            docker_source_release = None

        context = self._empty_context(
            release,
            release_root,
        )

        context["release"]["docker_source_release"] = (
            str(docker_source_release) if docker_source_release is not None else None
        )

        context["release"]["docker_dest_repo"] = str(
            docker_repository,
        )

        images: dict[str, dict[str, Any]] = {}

        for component_name in definition.children:

            component = definition.component(
                component_name,
            )

            if component is None:
                continue

            if component_name == "docker":

                images = self._analyse_docker(
                    root=release_root,
                    definition=component,
                    repository=docker_repository,
                    image_tag=image_tag,
                )

                context["images"] = images

            elif component_name == "openshift":

                openshift = self._analyse_openshift(
                    root=release_root,
                    definition=component,
                    repository=yaml_repository,
                    resource_index=resource_index,
                )

                self._merge_deployment_context(
                    context["deployment"],
                    openshift,
                )

                context["common_paths"] = self._analyse_common_paths(
                    root=release_root,
                    definition=component,
                )

            elif component_name == "database":

                context["database"] = self._analyse_database(
                    root=release_root,
                    definition=component,
                )

            else:

                self._log.debug(
                    f"No analyser registered for " f"component '{component_name}'.",
                )

        deployment = self._build_deployment_context(
            images=images,
            yaml_repository=yaml_repository,
            index=resource_index,
            existing_resources=context["deployment"]["resources"],
        )

        self._merge_deployment_context(
            context["deployment"],
            deployment,
        )

        transfer = self._build_transfer_deployment_context(
            images=self._analyse_image_transfer(
                release_root / image_transfer_script,
            ),
            yaml_repository=yaml_repository,
            index=resource_index,
            existing_resources=context["deployment"]["resources"],
        )

        self._merge_deployment_context(
            context["deployment"],
            transfer,
        )

        return context

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def _empty_context(
        self,
        release: Path,
        release_root: Path,
    ) -> dict[str, Any]:

        return {
            "workspace": None,
            "release": {
                "package": str(release),
                "root": str(release_root),
                "docker_source_release": None,
                "docker_dest_repo": "",
            },
            "images": {},
            "deployment": {
                "required": False,
                "resources": self._empty_resources(),
                "operations": self._empty_operations(),
            },
            "common_paths": [],
            "database": {
                "dir": None,
                "scripts": [],
                "execution_plan": None,
                "schemas": [],
            },
        }

    @staticmethod
    def _empty_resources() -> dict[str, list]:

        return {
            "deployments": [],
            "configmaps": [],
            "secrets": [],
            "services": [],
            "routes": [],
        }

    @staticmethod
    def _empty_operations() -> dict[str, list[str]]:

        return {
            "create": [],
            "apply": [],
            "replace": [],
        }

    # ------------------------------------------------------------------
    # Validation / extraction
    # ------------------------------------------------------------------

    def _validate_release(
        self,
        release: Path,
    ) -> None:

        if not self._filesystem.exists(
            release,
        ):
            raise ContextBuilderPluginException(
                f"Release archive not found: {release}",
            )

        if release.suffix.casefold() != ".zip":
            raise ContextBuilderPluginException(
                f"Release must be a ZIP archive: {release}",
            )

    def _extract(
        self,
        release: Path,
    ) -> Path:

        destination = release.with_suffix("")

        if self._filesystem.exists(
            destination,
        ):
            self._filesystem.remove(
                destination,
            )

        with self._activity(
            "Extract release",
        ):

            extracted = self._archive.extract(
                release,
                destination,
            )

        return Path(
            extracted,
        ).resolve()

    # ------------------------------------------------------------------
    # Docker
    # ------------------------------------------------------------------

    def _analyse_docker(
        self,
        *,
        root: Path,
        definition: dict[str, Any],
        repository: Path,
        image_tag: str,
    ) -> dict[str, dict[str, Any]]:

        docker_root = self._structures.path(
            root,
            definition,
        )

        if docker_root is None:
            return {}

        service_definition = self._structures.child(
            definition,
            "service",
        )

        if service_definition is None:
            return {}

        image_definition = self._structures.child(
            service_definition,
            "image",
        )

        if image_definition is None:
            return {}

        dockerfile_definition = image_definition.get(
            "dockerfile",
            {},
        )

        if not isinstance(
            dockerfile_definition,
            dict,
        ):
            raise ContextBuilderPluginException(
                "Docker image requires a " "'dockerfile' definition.",
            )

        dockerfile_name = dockerfile_definition.get(
            "name",
        )

        if (
            not isinstance(
                dockerfile_name,
                str,
            )
            or not dockerfile_name.strip()
        ):

            raise ContextBuilderPluginException(
                "Dockerfile name must be " "a non-empty string.",
            )

        result: dict[str, dict[str, Any]] = {}

        for service in self._directories(
            docker_root,
        ):

            image_root = self._structures.resolve(
                service,
                service_definition,
                "image",
            )

            if image_root is None:
                continue

            dockerfile = self._find_child_file(
                image_root,
                dockerfile_name,
            )

            if dockerfile is None:

                self._log.debug(
                    f"Dockerfile '{dockerfile_name}' " f"not found for '{service.name}'.",
                )

                pass

            repository_service = repository / service.name

            repository_image = repository_service / "image"

            if not self._changes.directory_changed(
                image_root,
                repository_image,
            ):
                continue

            result[service.name] = {
                "dockerfile": str(
                    repository_image / dockerfile_name,
                ),
                "context": str(
                    repository_service,
                ),
                "image_name": service.name,
                "image_tag": image_tag,
            }

            self._message.info(
                f"Docker build required for " f"'{service.name}'.",
            )

        return result

    # ------------------------------------------------------------------
    # Deployment
    # ------------------------------------------------------------------

    def _build_deployment_context(
        self,
        *,
        images: dict[str, dict[str, Any]],
        yaml_repository: Path,
        index: dict[str, Any],
        existing_resources: dict[str, list],
    ) -> dict[str, Any]:
        """
        Correlate Docker images with Deployment resources.

        OpenShift analysis is authoritative for resource existence and
        action. Existing indexed Deployments are used only as the fallback
        for an image-only change where the OpenShift YAML itself is
        unchanged.
        """

        result = {
            "required": False,
            "resources": self._empty_resources(),
            "operations": self._empty_operations(),
        }

        # if not images:
        #     return result

        deployments = existing_resources.get(
            "deployments",
            [],
        )

        for image_name, image in images.items():

            deployment_resource = self._find_context_deployment(
                deployments,
                image_name,
            )

            if deployment_resource is not None:

                if not self._enrich_context_deployment(
                    deployment_resource,
                    image_name=image_name,
                    image=image,
                ):
                    continue

                action = deployment_resource.get(
                    "action",
                )

                if action == "UPDATE":

                    match = self._resource_index.find_deployment(
                        index,
                        image_name,
                    )

                    if match is None:
                        raise ContextBuilderPluginException(
                            f"Deployment UPDATE resource "
                            f"'{deployment_resource.get('name')}' "
                            f"could not be resolved from the "
                            f"resource index.",
                        )

                    file = match.get(
                        "file",
                    )

                    if (
                        not isinstance(
                            file,
                            str,
                        )
                        or not file.strip()
                    ):
                        raise ContextBuilderPluginException(
                            f"Deployment UPDATE resource "
                            f"'{deployment_resource.get('name')}' "
                            f"does not have a valid file in "
                            f"the resource index.",
                        )

                    deployment_resource["file"] = file
                    deployment_resource["repository"] = str(
                        yaml_repository,
                    )

                    operation = "apply"
                    operation_path = str(
                        yaml_repository / file,
                    )

                elif action == "CREATE":

                    operation = "create"
                    operation_path = deployment_resource["repository"]

                else:

                    operation = self._deployment_operation(
                        action,
                    )

                    if operation is None:
                        continue

                    operation_path = deployment_resource["repository"]

                self._add_operation(
                    result["operations"],
                    operation,
                    operation_path,
                )

                continue

            match = self._resource_index.find_deployment(
                index,
                image_name,
            )

            if match is None:

                self._log.warning(
                    f"No deployment found for image " f"'{image_name}'.",
                )

                continue

            current_image = match["current_image"].strip()
            target_image = self._retag_image(
                current_image,
                image["image_tag"],
            )

            deployment_resource = {
                "name": match["deployment"],
                "kind": "Deployment",
                "action": "UPDATE",
                "file": match["file"],
                "repository": str(yaml_repository),
                "container": match["container"],
                "current_image": current_image,
                "target_image": target_image,
            }

            result["resources"]["deployments"].append(
                deployment_resource,
            )

            self._add_operation(
                result["operations"],
                "apply",
                str(yaml_repository / match["file"]),
            )

        result["required"] = bool(
            result["resources"]["deployments"] or any(result["operations"].values())
        )

        return result

    # ------------------------------------------------------------------
    # Image transfer
    # ------------------------------------------------------------------

    def _analyse_image_transfer(
        self,
        script: Path,
    ) -> list[str]:
        """
        Images pushed by the release's image transfer script.

        Only 'docker push <image>' / 'docker image push <image>' commands are
        read (also after 'sudo' or a shell separator such as '&&'); the
        script is never run.
        """

        if not self._filesystem.exists(script) or not self._filesystem.is_file(script):

            self._log.debug(
                f"No image transfer script at '{script}'.",
            )

            return []

        images: list[str] = []

        for line in self._filesystem.read_text(script).splitlines():

            for image in self._pushed_images(
                line,
            ):

                if "$" in image:
                    self._log.warning(
                        f"Skipped image transfer push with a shell variable: '{image}'.",
                    )
                    continue

                if image not in images:
                    images.append(image)

        return images

    def _pushed_images(
        self,
        line: str,
    ) -> list[str]:
        """
        Return the images pushed by Docker commands on one shell line.
        """

        if "push" not in line:
            return []

        lexer = shlex.shlex(
            line,
            posix=True,
            punctuation_chars=True,
        )
        lexer.whitespace_split = True

        try:

            tokens = list(
                lexer,
            )

        except ValueError as exc:

            self._log.warning(
                f"Skipped unparseable image transfer line '{line.strip()}': {exc}",
            )

            return []

        commands: list[list[str]] = [[]]

        for token in tokens:

            if token in self.SHELL_SEPARATORS:
                commands.append([])
            else:
                commands[-1].append(token)

        images: list[str] = []

        for command in commands:

            image = self._docker_push_image(
                command,
            )

            if image is not None:
                images.append(image)

        return images

    @classmethod
    def _docker_push_image(
        cls,
        command: list[str],
    ) -> str | None:
        """
        Return the image argument of a 'docker [image] push' command.
        """

        if command[:1] == ["sudo"]:

            command = command[1:]

            while command and command[0].startswith("-"):
                command = command[1:]

        if command[:2] == ["docker", "push"]:
            arguments = command[2:]

        elif command[:3] == ["docker", "image", "push"]:
            arguments = command[3:]

        else:
            return None

        skip_value = False

        for argument in arguments:

            if skip_value:
                skip_value = False
                continue

            if argument in cls.DOCKER_PUSH_VALUE_OPTIONS:
                skip_value = True
                continue

            if argument.startswith("-"):
                continue

            return argument

        return None

    def _build_transfer_deployment_context(
        self,
        *,
        images: list[str],
        yaml_repository: Path,
        index: dict[str, Any],
        existing_resources: dict[str, list],
    ) -> dict[str, Any]:
        """
        Correlate images pushed by the image transfer script with indexed
        Deployments. The Deployment keeps its registry; only the tag changes.
        """

        result: dict[str, Any] = {
            "required": False,
            "resources": self._empty_resources(),
            "operations": self._empty_operations(),
        }

        updated = {
            (resource.get("name"), resource.get("container"))
            for resource in existing_resources.get("deployments", [])
            if isinstance(resource, dict) and resource.get("target_image")
        }

        for image in images:

            repository = self._image_repository(
                image,
            )

            if "@" in image or len(image) <= len(repository) + 1:
                self._log.warning(
                    f"Skipped image transfer image without a tag: '{image}'.",
                )
                continue

            tag = image[len(repository) + 1 :]

            match = self._resource_index.find_deployment(
                index,
                self._image_path(repository),
            )

            if match is None:

                match = self._find_transfer_deployment_by_name(
                    index,
                    image,
                    repository,
                )

            if match is None:
                continue

            if (match["deployment"], match["container"]) in updated:
                continue

            current_image = match["current_image"].strip()

            result["resources"]["deployments"].append(
                {
                    "name": match["deployment"],
                    "kind": "Deployment",
                    "action": "UPDATE",
                    "file": match["file"],
                    "repository": str(yaml_repository),
                    "container": match["container"],
                    "current_image": current_image,
                    "target_image": self._retag_image(
                        current_image,
                        tag,
                    ),
                    "image_transfer": True,
                },
            )

            updated.add(
                (match["deployment"], match["container"]),
            )

            self._add_operation(
                result["operations"],
                "apply",
                str(yaml_repository / match["file"]),
            )

        result["required"] = bool(
            result["resources"]["deployments"],
        )

        return result

    def _find_transfer_deployment_by_name(
        self,
        index: dict[str, Any],
        image: str,
        repository: str,
    ) -> dict[str, Any] | None:
        """
        Fallback for a pushed image whose registry/namespace path differs
        from the Deployment's image (for example the Deployment pulls from
        the internal OpenShift registry). Matches on the final image name
        only when exactly one Deployment container uses that name.
        """

        name = repository.rsplit("/", 1)[-1]

        matches = self._resource_index.find_deployments_by_name(
            index,
            name,
        )

        if len(matches) == 1:

            self._log.warning(
                f"Transferred image '{image}' matched Deployment "
                f"'{matches[0]['deployment']}' by image name '{name}' only; "
                f"its current image is '{matches[0]['current_image']}'.",
            )

            return matches[0]

        if matches:

            candidates = ", ".join(
                sorted(str(match["deployment"]) for match in matches),
            )

            self._log.warning(
                f"Transferred image '{image}' did not match any Deployment by "
                f"path, and image name '{name}' is used by several "
                f"Deployments ({candidates}); none was updated.",
            )

            return None

        self._log.warning(
            f"No deployment found for transferred image " f"'{image}'.",
        )

        return None

    @staticmethod
    def _image_path(
        repository: str,
    ) -> str:
        """
        Return an image repository without its registry host.
        """

        first, _, rest = repository.partition("/")

        if rest and ("." in first or ":" in first or first == "localhost"):
            return rest

        return repository

    def _find_context_deployment(
        self,
        deployments: list,
        image_name: str,
    ) -> dict[str, Any] | None:
        """
        Find a Deployment context resource containing the image.
        """

        matches: list[dict[str, Any]] = []

        for resource in deployments:

            if not isinstance(resource, dict):
                continue

            kind = resource.get("kind")
            source = resource.get("source")

            if (
                not isinstance(kind, str)
                or kind.casefold()
                not in {
                    "deployment",
                    "deploymentconfig",
                }
                or not isinstance(source, str)
                or not source.strip()
            ):
                continue

            if (
                self._find_container_image(
                    Path(source),
                    image_name,
                )
                is not None
            ):
                matches.append(resource)

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 1:
            self._log.warning(
                f"Multiple deployments found for image " f"'{image_name}'.",
            )

        return None

    def _enrich_context_deployment(
        self,
        resource: dict[str, Any],
        *,
        image_name: str,
        image: dict[str, Any],
    ) -> bool:
        """
        Add Docker image metadata to a Deployment context resource.
        """

        source = resource.get("source")

        if not isinstance(source, str) or not source.strip():
            return False

        match = self._find_container_image(
            Path(source),
            image_name,
        )

        if match is None:
            self._log.warning(
                f"No container image found for Docker image "
                f"'{image_name}' in deployment "
                f"'{resource.get('name', source)}'.",
            )
            return False

        container_name, current_image = match
        resource["container"] = container_name

        if resource.get("action") == "UPDATE":
            resource["current_image"] = current_image

        resource["target_image"] = self._retag_image(
            current_image,
            image["image_tag"],
        )

        return True

    def _find_container_image(
        self,
        source: Path,
        image_name: str,
    ) -> tuple[str, str] | None:
        """
        Find the container that references a Docker image.
        """

        if not self._filesystem.exists(source):
            return None

        documents = self._filesystem.load_yaml_documents(
            self._filesystem.read_text(source),
        )

        candidates: list[tuple[str, str, bool]] = []

        for document in documents:

            if not isinstance(document, dict):
                continue

            kind = document.get("kind")

            if not isinstance(kind, str) or kind.casefold() not in {
                "deployment",
                "deploymentconfig",
            }:
                continue

            spec = document.get("spec")

            if not isinstance(spec, dict):
                continue

            template = spec.get("template")

            if not isinstance(template, dict):
                continue

            pod_spec = template.get("spec")

            if not isinstance(pod_spec, dict):
                continue

            containers = pod_spec.get("containers", [])

            if not isinstance(containers, list):
                continue

            for container in containers:

                if not isinstance(container, dict):
                    continue

                name = container.get("name")
                image = container.get("image")

                if not isinstance(name, str) or not isinstance(image, str):
                    continue

                exact_name = name.casefold() == image_name.casefold()
                image_repository = self._image_repository(image)
                image_basename = image_repository.rsplit("/", 1)[-1]

                if exact_name or image_basename.casefold() == image_name.casefold():
                    candidates.append((name, image, exact_name))

        exact = [candidate for candidate in candidates if candidate[2]]

        if len(exact) == 1:
            return exact[0][0], exact[0][1]

        if len(exact) > 1:
            return None

        if len(candidates) == 1:
            return candidates[0][0], candidates[0][1]

        return None

    @staticmethod
    def _image_repository(image: str) -> str:
        """
        Return an image reference without its tag or digest.
        """

        repository = image.strip().split("@", 1)[0]
        last_component = repository.rsplit("/", 1)[-1]

        if ":" in last_component:
            return repository.rsplit(":", 1)[0]

        return repository

    @classmethod
    def _retag_image(
        cls,
        image: str,
        tag: str,
    ) -> str:
        """
        Replace an image tag or digest while preserving its repository.
        """

        return f"{cls._image_repository(image)}:{tag.strip()}"

    @staticmethod
    def _deployment_operation(
        action: str,
    ) -> str | None:
        """
        Map a Deployment action to its execution operation.
        """

        return {
            "CREATE": "create",
            "UPDATE": "apply",
        }.get(action.upper())

    @staticmethod
    def _add_operation(
        operations: dict[str, list[str]],
        operation: str,
        path: str,
    ) -> None:
        """
        Add an operation path once.
        """

        if path not in operations[operation]:
            operations[operation].append(path)

    def _merge_deployment_context(
        self,
        target: dict[str, Any],
        source: dict[str, Any],
    ) -> None:

        target_resources = target["resources"]

        source_resources = source.get(
            "resources",
            {},
        )

        for category in target_resources:

            target_resources[category].extend(
                source_resources.get(
                    category,
                    [],
                ),
            )

        target_operations = target.setdefault(
            "operations",
            self._empty_operations(),
        )

        source_operations = source.get(
            "operations",
            {},
        )

        for operation in (
            "create",
            "apply",
            "replace",
        ):

            for path in source_operations.get(
                operation,
                [],
            ):

                if path not in target_operations[operation]:

                    target_operations[operation].append(
                        path,
                    )

        target["required"] = any(
            target_resources.values(),
        )

    # ------------------------------------------------------------------
    # OpenShift
    # ------------------------------------------------------------------

    def _analyse_openshift(
        self,
        *,
        root: Path,
        definition: dict[str, Any],
        repository: Path,
        resource_index: dict[str, Any],
    ) -> dict[str, Any]:

        yamls_root = self._structures.resolve(
            root,
            definition,
            "yamls",
        )

        if yamls_root is None:

            return {
                "required": False,
                "resources": self._empty_resources(),
                "operations": self._empty_operations(),
            }

        resources = self._empty_resources()

        operations = self._empty_operations()

        for source in self._yaml_files(
            yamls_root,
        ):

            documents = self._filesystem.load_yaml_documents(
                self._filesystem.read_text(
                    source,
                ),
            )

            for document in documents:

                if not isinstance(
                    document,
                    dict,
                ):
                    continue

                kind = document.get(
                    "kind",
                )

                if isinstance(kind, str):
                    normalized_kind = kind.casefold()

                    if normalized_kind == "configmapsecretupdate":
                        self._analyse_cmsecret_document(
                            document=document,
                            source=source,
                            repository=repository,
                            resources=resources,
                            operations=operations,
                            resource_index=resource_index,
                        )

                    elif normalized_kind == "deploymentupdate":
                        self._analyse_deployment_update_document(
                            document=document,
                            source=source,
                            repository=repository,
                            resources=resources,
                            operations=operations,
                            resource_index=resource_index,
                        )

                    else:
                        self._analyse_openshift_document(
                            document=document,
                            source=source,
                            repository=repository,
                            resources=resources,
                            operations=operations,
                            resource_index=resource_index,
                        )

        return {
            "required": any(
                resources.values(),
            ),
            "resources": resources,
            "operations": operations,
        }

    # ------------------------------------------------------------------
    # Deployment
    # ------------------------------------------------------------------

    def _analyse_deployment_update_document(
        self,
        *,
        document: dict[str, Any],
        source: Path,
        repository: Path,
        resources: dict[str, list],
        operations: dict[str, list[str]],
        resource_index: dict[str, Any],
    ) -> None:
        """Analyse an explicit DeploymentUpdate definition."""

        target = document.get("target")

        if not isinstance(target, dict):
            self._log.warning(
                f"DeploymentUpdate '{source}' does not contain a valid target.",
            )
            return

        kind = target.get("kind")
        name = target.get("name")

        if not isinstance(kind, str) or not isinstance(name, str):
            self._log.warning(
                f"DeploymentUpdate '{source}' has an invalid target.",
            )
            return

        if kind.casefold() not in {
            "deployment",
            "deploymentconfig",
        }:
            self._log.warning(
                f"DeploymentUpdate '{source}' targets unsupported "
                f"kind '{kind}'.",
            )
            return

        indexed_resource = self._resource_index.find_resource(
            resource_index,
            kind=kind,
            name=name,
        )

        if indexed_resource is None:
            raise ContextBuilderPluginException(
                f"DeploymentUpdate target '{kind}/{name}' "
                f"was not found in the resource index.",
            )

        file = indexed_resource.get("file")

        if not isinstance(file, str) or not file.strip():
            raise ContextBuilderPluginException(
                f"DeploymentUpdate target '{kind}/{name}' "
                f"does not have a valid repository file.",
            )

        # repository_path = repository / file

        source_operations = document.get(
            "operations",
            [],
        )

        if not isinstance(source_operations, list):
            raise ContextBuilderPluginException(
                f"DeploymentUpdate '{source}' has invalid "
                f"'operations'.",
            )

        resources["deployments"].append(
            {
                "name": name,
                "kind": kind,
                "action": "UPDATE",
                "source": str(source),
                "repository": str(repository),
                "file": file,
                "operations": source_operations,
                "deployment_update": True,
            },
        )

        self._add_operation(
            operations,
            "apply",
            str(repository),
        )

        self._message.info(
            f"Deployment update required for '{kind}/{name}'.",
        )

    # ------------------------------------------------------------------
    # ConfigMap / Secret
    # ------------------------------------------------------------------

    def _analyse_cmsecret_document(
        self,
        *,
        document: dict[str, Any],
        source: Path,
        repository: Path,
        operations: dict[str, list[str]],
        resources: dict[str, list],
        resource_index: dict[str, Any],
    ) -> None:

        target = document.get(
            "target",
            {},
        )

        if not isinstance(target, dict):
            return

        kind = target.get("kind")
        name = target.get("name")

        if not isinstance(kind, str) or not isinstance(name, str):
            return

        category = {
            "configmap": "configmaps",
            "secret": "secrets",
        }.get(kind.casefold())

        if category is None:
            return

        indexed_resource = self._resource_index.find_resource(
            resource_index,
            kind=kind,
            name=name,
        )

        if indexed_resource is None:

            self._log.warning(
                f"No repository resource found for " f"{kind}/{name}.",
            )

            return

        source_operations = document.get(
            "operations",
            [],
        )

        if not isinstance(
            source_operations,
            list,
        ):
            source_operations = []

        repository_path = repository / indexed_resource["file"]

        resources[category].append(
            {
                "name": name,
                "kind": kind,
                "action": "UPDATE",
                "source": str(source),
                "repository": str(repository_path),
                "operations": source_operations,
            },
        )

        operations["replace"].append(
            str(repository_path),
        )

    # ------------------------------------------------------------------
    # Standard OpenShift resources
    # ------------------------------------------------------------------

    def _analyse_openshift_document(
        self,
        *,
        document: dict[str, Any],
        source: Path,
        repository: Path,
        resources: dict[str, list],
        operations: dict[str, list[str]],
        resource_index: dict[str, Any],
    ) -> None:

        kind = document.get(
            "kind",
        )

        metadata = document.get(
            "metadata",
            {},
        )

        if not isinstance(
            kind,
            str,
        ):
            return

        if not isinstance(
            metadata,
            dict,
        ):
            metadata = {}

        name = metadata.get(
            "name",
            source.stem,
        )

        if not isinstance(
            name,
            str,
        ):
            name = source.stem

        category = self._resource_category(
            kind,
        )

        if category is None:
            return

        indexed_resource = self._resource_index.find_resource(
            resource_index,
            kind=kind,
            name=name,
        )

        if indexed_resource is not None:

            target = repository / indexed_resource["file"]

        else:

            target = repository / category / f"{name}.yaml"

        action = self._resource_action(
            source,
            target,
        )

        if action == "UNCHANGED":
            return

        resources[category].append(
            {
                "name": name,
                "kind": kind,
                "action": action,
                "source": str(source),
                "repository": str(target),
            },
        )

        operation = self._deployment_operation(
            action,
        )

        if operation is not None:
            self._add_operation(
                operations,
                operation,
                str(target),
            )

    @staticmethod
    def _resource_category(
        kind: str,
    ) -> str | None:

        return {
            "deployment": "deployments",
            "deploymentconfig": "deployments",
            "configmap": "configmaps",
            "secret": "secrets",
            "service": "services",
            "route": "routes",
        }.get(
            kind.casefold(),
        )

    def _resource_action(
        self,
        source: Path,
        target: Path,
    ) -> str:

        if not self._filesystem.exists(
            target,
        ):
            return "CREATE"

        if self._changes.file_changed(
            source,
            target,
        ):
            return "UPDATE"

        return "UNCHANGED"

    # ------------------------------------------------------------------
    # Common path / Rsync
    # ------------------------------------------------------------------

    def _analyse_common_paths(
        self,
        *,
        root: Path,
        definition: dict[str, Any],
    ) -> list[dict[str, Any]]:

        common_definition = self._structures.child(
            definition,
            "common_path",
        )

        if common_definition is None:
            return []

        common_root = self._structures.resolve(
            root,
            definition,
            "common_path",
        )

        if common_root is None:
            return []

        plan_definition = common_definition.get(
            "rsync_plan",
            {},
        )

        plan_file = self._find_plan_file(
            common_root,
            plan_definition,
            "rsync_plan",
        )

        if plan_file is None:
            return []

        plan = self._load_plan(
            plan_file,
        )

        if not isinstance(
            plan,
            dict,
        ):
            return []

        entries = plan.get(
            "plans",
            [],
        )

        if not isinstance(
            entries,
            list,
        ):
            return []

        result = []

        for entry in entries:

            if not isinstance(
                entry,
                dict,
            ):
                continue

            source = entry.get(
                "source",
            )

            if not isinstance(
                source,
                str,
            ):
                continue

            resolved = dict(
                entry,
            )

            resolved["source"] = str(
                common_root / source,
            )

            result.append(
                resolved,
            )

        return result

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _analyse_database(
        self,
        *,
        root: Path,
        definition: dict[str, Any],
    ) -> dict[str, Any]:

        database_root = self._structures.path(
            root,
            definition,
        )

        if database_root is None:

            return {
                "scripts": [],
                "execution_plan": None,
                "schemas": [],
            }

        scripts_definition = definition.get(
            "scripts",
            {},
        )

        if not isinstance(
            scripts_definition,
            dict,
        ):
            scripts_definition = {}

        extensions = {
            extension.casefold()
            for extension in scripts_definition.get(
                "extensions",
                [".sql"],
            )
            if isinstance(
                extension,
                str,
            )
        }

        scripts = []

        for path in self._files(
            database_root,
        ):

            if path.suffix.casefold() not in extensions:
                continue

            scripts.append(
                {
                    "application": path.parent.name,
                    # Folder under DBScripts: "App1", or "H01/App1" when
                    # applications are grouped; plan keys match this.
                    "directory": path.parent.relative_to(
                        database_root,
                    ).as_posix(),
                    "script": str(path),
                },
            )

        execution_definition = definition.get(
            "execution_plan",
            {},
        )

        execution_plan = None

        plan_file = self._find_plan_file(
            database_root,
            execution_definition,
            "execution_plan",
        )

        if plan_file is not None:
            execution_plan = self._load_plan(
                plan_file,
            )

        return {
            "dir": str(database_root),
            "scripts": scripts,
            "execution_plan": execution_plan,
            # What the release changes, so later steps (an invalid objects
            # report, say) can look at these schemas only.
            "schemas": self._plan_schemas(
                execution_plan,
            ),
        }

    @staticmethod
    def _plan_schemas(
        execution_plan: Any,
    ) -> list[str]:
        """
        The schemas the execution plan's applications run in, in plan order.
        """

        if not isinstance(
            execution_plan,
            dict,
        ):
            return []

        applications = execution_plan.get(
            "applications",
        )

        if not isinstance(
            applications,
            dict,
        ):
            return []

        schemas: list[str] = []

        for definition in applications.values():

            schema = definition.get("schema") if isinstance(definition, dict) else None

            if isinstance(schema, str) and schema.strip() and schema.strip() not in schemas:
                schemas.append(schema.strip())

        return schemas

    # ------------------------------------------------------------------
    # Plan files
    # ------------------------------------------------------------------

    def _find_plan_file(
        self,
        root: Path,
        definition: Any,
        default_name: str,
    ) -> Path | None:

        if not isinstance(
            definition,
            dict,
        ):
            definition = {}

        names = definition.get(
            "names",
        )

        if isinstance(
            names,
            list,
        ):

            candidates = [
                name
                for name in names
                if isinstance(
                    name,
                    str,
                )
            ]

        else:

            name = definition.get(
                "name",
            )

            if isinstance(
                name,
                str,
            ):
                candidates = [name]

            else:

                candidates = [
                    f"{default_name}.yaml",
                    f"{default_name}.yml",
                    f"{default_name}.json",
                ]

        for name in candidates:

            path = self._find_child_file(
                root,
                name,
            )

            if path is not None:
                return path

        return None

    def _load_plan(
        self,
        path: Path,
    ) -> Any:
        """
        Load a YAML or JSON execution plan.
        """

        content = self._filesystem.read_text(
            path,
        )

        suffix = path.suffix.casefold()

        if suffix == ".json":
            return self._filesystem.parse_json(
                content,
            )

        if suffix in {
            ".yaml",
            ".yml",
        }:
            return self._filesystem.parse_yaml(
                content,
            )

        raise ContextBuilderPluginException(
            f"Unsupported plan format: {path}",
        )

    # ------------------------------------------------------------------
    # Filesystem
    # ------------------------------------------------------------------

    def _directories(
        self,
        root: Path,
    ) -> list[Path]:

        if not self._filesystem.exists(
            root,
        ):
            return []

        return [
            path
            for path in self._filesystem.listdir(
                root,
            )
            if (self._filesystem.is_directory(path) and not self._ignored(path))
        ]

    def _files(
        self,
        root: Path,
    ) -> list[Path]:

        if not self._filesystem.exists(
            root,
        ):
            return []

        return [
            path
            for path in self._filesystem.find(
                root,
                pattern="*",
                recursive=True,
            )
            if (self._filesystem.is_file(path) and not self._ignored(path))
        ]

    def _yaml_files(
        self,
        root: Path,
    ) -> list[Path]:

        return [
            path
            for path in self._files(
                root,
            )
            if path.suffix.casefold() in self.YAML_EXTENSIONS
        ]

    def _find_child_file(
        self,
        root: Path,
        name: str,
    ) -> Path | None:

        if not self._filesystem.exists(
            root,
        ):
            return None

        for path in self._filesystem.listdir(
            root,
        ):

            if self._filesystem.is_file(path) and path.name.casefold() == name.casefold():
                return path

        return None

    @staticmethod
    def _ignored(
        path: Path,
    ) -> bool:

        return (
            path.name == "__MACOSX"
            or path.name == ".DS_Store"
            or path.name.startswith("._")
            or path.name.startswith(".gitignore")
        )

    def _resolve_deployment_target(
        self,
        *,
        repository: Path,
        kind: str,
        name: str,
    ) -> Path | None:
        """
        Resolve a ConfigMap/Secret target through deployment
        references.
        """

        deployments_root = repository / "deployments"

        if not self._filesystem.exists(deployments_root):
            return None

        for deployment_file in self._yaml_files(
            deployments_root,
        ):
            try:
                documents = self._filesystem.load_yaml_documents(
                    self._filesystem.read_text(
                        deployment_file,
                    ),
                )
            except Exception:
                continue

            for document in documents:

                if not isinstance(document, dict):
                    continue

                spec = document.get("spec")

                if not isinstance(spec, dict):
                    continue

                template = spec.get("template")

                if not isinstance(template, dict):
                    continue

                pod_spec = template.get("spec")

                if not isinstance(pod_spec, dict):
                    continue

                if not self._deployment_references_resource(
                    pod_spec,
                    kind=kind,
                    name=name,
                ):
                    continue

                target = (
                    repository
                    / ("configmaps" if kind.casefold() == "configmap" else "secrets")
                    / self._resource_filename(
                        repository=repository,
                        kind=kind,
                        name=name,
                    )
                )

                if self._filesystem.exists(target):
                    return target

        return None

    def find_resource(
        self,
        index: dict[str, Any],
        *,
        kind: str,
        name: str,
    ) -> dict[str, Any] | None:

        resources = index.get("resources", {})

        if not isinstance(resources, dict):
            return None

        kind_resources = resources.get(kind)

        if not isinstance(kind_resources, dict):
            return None

        resource = kind_resources.get(name)

        if not isinstance(resource, dict):
            return None

        return resource
