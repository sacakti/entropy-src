"""
Release package analyser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import ContextBuilderPluginException
from .resource_index import ResourceIndex
from .detector import ReleaseChangeDetector
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
    ) -> dict[str, Any]:

        release = release.expanduser().resolve()
        structure = structure.expanduser().resolve()
        resource_index = self._resource_index.load(
            yaml_repository,
        )
        self._validate_release(
            release,
        )

        release_root = self._extract(
            release,
        )

        definition = self._structures.load(
            structure,
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
            str(docker_source_release)
            if docker_source_release is not None
            else None
        )

        context["release"]["docker_dest_repo"] = str(
            docker_repository,
        )

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

                deployment = (
                    self._build_deployment_context(
                        images=images,
                        yaml_repository=yaml_repository,
                        index=resource_index
                    )
                )

                self._merge_deployment_context(
                    context["deployment"],
                    deployment,
                )

            elif component_name == "openshift":

                openshift = self._analyse_openshift(
                    root=release_root,
                    definition=component,
                    repository=yaml_repository,
                    resource_index=resource_index
                )

                self._merge_deployment_context(
                    context["deployment"],
                    openshift,
                )

                context["common_paths"] = (
                    self._analyse_common_paths(
                        root=release_root,
                        definition=component,
                    )
                )

            elif component_name == "database":

                context["database"] = (
                    self._analyse_database(
                        root=release_root,
                        definition=component,
                    )
                )

            else:

                self._log.debug(
                    f"No analyser registered for "
                    f"component '{component_name}'.",
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
                "operations": {
                    "apply": [],
                    "replace": [],
                },
            },
            "common_paths": [],
            "database": {
                "scripts": [],
                "execution_plan": None,
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
                "Docker image requires a "
                "'dockerfile' definition.",
            )

        dockerfile_name = dockerfile_definition.get(
            "name",
        )

        if not isinstance(
            dockerfile_name,
            str,
        ) or not dockerfile_name.strip():

            raise ContextBuilderPluginException(
                "Dockerfile name must be "
                "a non-empty string.",
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
                    f"Dockerfile '{dockerfile_name}' "
                    f"not found for '{service.name}'.",
                )

                pass

            repository_service = (
                repository
                / service.name
            )

            repository_image = (
                repository_service
                / "image"
            )

            if not self._changes.directory_changed(
                image_root,
                repository_image,
            ):
                continue

            result[service.name] = {
                "dockerfile": str(
                    repository_image
                    / dockerfile_name,
                ),
                "context": str(
                    repository_service,
                ),
                "image_name": service.name,
                "image_tag": image_tag,
            }

            self._message.info(
                f"Docker build required for "
                f"'{service.name}'.",
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
    ) -> dict[str, Any]:

        result = {
            "required": False,
            "resources": self._empty_resources(),
            "operations": {
                "apply": [],
                "replace": [],
            },
        }

        if not images:
            return result

        for image_name, image in images.items():

            match = self._resource_index.find_deployment(
                index,
                image_name,
            )

            if match is None:

                self._log.warning(
                    f"No deployment found for image "
                    f"'{image_name}'.",
                )

                continue

            current_image = match["current_image"].strip()

            repository_name, separator, tag = (
                current_image.rpartition(":")
            )

            if separator:
                current_image = (
                    f"{repository_name.strip()}:"
                    f"{tag.strip()}"
                )

            image_repository = current_image.rsplit(
                ":",
                1,
            )[0]

            target_image = (
                f"{image_repository}:"
                f"{image['image_tag']}"
            )

            result["resources"]["deployments"].append(
                {
                    "name": match["deployment"],
                    "file": match["file"],
                    "container": match["container"],
                    "current_image": current_image,
                    "target_image": target_image,
                },
            )

            deployment_path = str(
                yaml_repository
                / match["file"]
            )

            if deployment_path not in result["operations"]["apply"]:

                result["operations"]["apply"].append(
                    deployment_path,
                )

        result["required"] = bool(
            result["resources"]["deployments"],
        )

        return result

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
            {
                "apply": [],
                "replace": [],
            },
        )

        source_operations = source.get(
            "operations",
            {},
        )

        for operation in (
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
                "operations": {
                    "apply": [],
                    "replace": [],
                },
            }

        resources = self._empty_resources()

        operations = {
            "apply": [],
            "replace": [],
        }

        for source in self._yaml_files(
            yamls_root,
        ):

            documents = (
                self._filesystem.load_yaml_documents(
                    self._filesystem.read_text(
                        source,
                    ),
                )
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

                if (
                    isinstance(kind, str)
                    and kind.casefold()
                    == "configmapsecretupdate"
                ):

                    self._analyse_cmsecret_document(
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
                f"No repository resource found for "
                f"{kind}/{name}.",
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

        repository_path = (
            repository
            / indexed_resource["file"]
        )

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

            target = (
                repository
                / indexed_resource["file"]
            )

        else:

            target = (
                repository
                / category
                / f"{name}.yaml"
            )

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
            "scripts": scripts,
            "execution_plan": execution_plan,
        }

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
            if (
                self._filesystem.is_directory(path)
                and not self._ignored(path)
            )
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
            if (
                self._filesystem.is_file(path)
                and not self._ignored(path)
            )
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
            if path.suffix.casefold()
            in self.YAML_EXTENSIONS
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

            if (
                self._filesystem.is_file(path)
                and path.name.casefold()
                == name.casefold()
            ):
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
                    / (
                        "configmaps"
                        if kind.casefold() == "configmap"
                        else "secrets"
                    )
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
