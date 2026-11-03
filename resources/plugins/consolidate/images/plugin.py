"""
consolidate.images: the latest image of each service across several releases.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin
from lib.plugins.release_packages import (
    ReleasePackages,
    release_name,
)

from .exceptions import (
    ConsolidationException,
    ConsolidationIndexError,
    ConsolidationReleaseError,
)
from .transfer import (
    TransferImage,
    image_path,
    image_repository,
    parse_transfer_script,
    render_transfer_script,
)


@dataclass
class ServiceImage:
    """The latest release's image folder of a service."""

    name: str
    release: str
    order: int
    folder: Path


@dataclass
class TransferEntry:
    """The latest release's pushed image of a repository."""

    image: TransferImage
    release: str
    order: int


class ConsolidateImagesPlugin(
    BasePlugin,
):
    """
    Keep the latest image of each service across several release packages: images to
    build from `App/services` and images to transfer from `scripts/deploy`. Releases
    without images are skipped. Nothing is built, pushed or applied here.
    """

    SERVICES_LAYOUT = (("App", "services"),)
    SCRIPTS_LAYOUT = (("scripts", "deploy"),)

    IMAGE_FOLDER = "image"
    DOCKERFILE = "Dockerfile"
    TRANSFER_SCRIPT = "image_transfer.sh"
    APPLY_SCRIPT = "apply_yaml.sh"

    # Written by oc.sync_yamls.
    RESOURCE_INDEX = (".entropy", "resource_index.json")

    REPORT = "consolidation-report.json"

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
    ) -> PluginResult:
        """
        Consolidate the releases' images.
        """

        try:

            with self.activity(
                "consolidate-images",
            ):

                return self._execute()

        except ConsolidationException as exc:

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
                    {
                        "message": str(exc),
                    },
                ],
            )

    def _execute(
        self,
    ) -> PluginResult:

        packages = ReleasePackages(
            self.filesystem,
            self.archive,
            Path(self.workspace) / "consolidate" / "images" / "releases",
            ConsolidationReleaseError,
        )

        releases = packages.resolve(
            self.arguments.path("release_directory"),
            self.arguments.list("releases"),
        )

        image_tag = str(self.arguments.string("image_tag") or "").strip()

        if not image_tag:

            raise ConsolidationReleaseError(
                "Argument 'image_tag' is required.",
            )

        docker_repository = self.arguments.path("docker_repository")
        yaml_repository = self.arguments.path("yaml_repository")

        # Before the output folder is emptied: a missing index is found first.
        index = self._load_index(yaml_repository) if yaml_repository else None

        output = packages.prepare_output(
            self.arguments.path(
                "output_directory",
                Path(self.workspace) / "consolidated" / "images",
            ),
            self.arguments.boolean("overwrite", False),
        )

        names = [release_name(path) for path in releases]

        self.message.info(
            f"Consolidating images of {len(releases)} release(s): " + ", ".join(names),
        )

        warnings: List[str] = []
        services: Dict[str, ServiceImage] = {}
        transfers: Dict[str, TransferEntry] = {}

        for order, release in enumerate(releases):

            root = packages.open(release)
            name = release_name(release)

            self._collect_services(packages, root, name, order, services, warnings)
            self._collect_transfers(packages, root, name, order, transfers, warnings)

        changed = [
            service
            for service in services.values()
            if self._needs_build(packages, service, docker_repository)
        ]

        images = {
            service.name: self._stage_service(packages, service, output, image_tag)
            for service in changed
        }

        script = output / self.TRANSFER_SCRIPT

        self.filesystem.write_text(
            script,
            render_transfer_script(entry.image for entry in transfers.values()),
        )

        deployments = (
            self._deployment_updates(
                changed, transfers, index, yaml_repository, image_tag, warnings
            )
            if index is not None and yaml_repository is not None
            else []
        )

        for warning in warnings:

            self.message.warning(
                warning,
            )

        report = output / self.REPORT

        self.filesystem.write_json(
            report,
            {
                "releases": names,
                "services": {
                    service.name: {
                        "release": service.release,
                        "build": service.name in images,
                    }
                    for service in services.values()
                },
                "transfers": {
                    repository: {
                        "release": entry.release,
                        "image": entry.image.image,
                    }
                    for repository, entry in transfers.items()
                },
                "deployments": deployments,
                "warnings": warnings,
            },
            indent=2,
            sort_keys=False,
        )

        self.artifacts["consolidation_report"] = report

        has_work = bool(images or transfers)

        self.outputs.update(
            {
                "output_directory": str(output),
                "report": str(report),
                "releases": names,
                "images": images,
                "transfer_script": str(script),
                "transfers": [entry.image.image for entry in transfers.values()],
                "deployments": deployments,
                "changed": has_work,
            },
        )

        if has_work:

            self.message.success(
                f"Consolidated {len(images)} image(s) to build and "
                f"{len(transfers)} to transfer into {output}.",
            )

        else:

            self.message.info(
                "No release has images to build or transfer.",
            )

        return self._result(
            success=True,
            changed=has_work,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def _collect_services(
        self,
        packages: ReleasePackages,
        root: Path,
        release: str,
        order: int,
        services: Dict[str, ServiceImage],
        warnings: List[str],
    ) -> None:
        """A later release's image folder replaces an earlier one as a whole."""

        folder = packages.find_folder(
            root,
            self.SERVICES_LAYOUT,
            release=release,
            label="App/services",
        )

        if folder is None:

            return

        for service in sorted(self.filesystem.listdir(folder)):

            image = service / self.IMAGE_FOLDER

            if not self.filesystem.is_directory(image) or not packages.files(image):

                continue

            earlier = services.get(service.name)

            if earlier is not None:

                dropped = sorted(
                    self._relative_files(packages, earlier.folder)
                    - self._relative_files(packages, image),
                )

                if dropped:

                    warnings.append(
                        f"Service '{service.name}': {release} replaces the image of "
                        f"{earlier.release}, so these files of {earlier.release} are not "
                        "included: " + ", ".join(dropped) + ".",
                    )

            services[service.name] = ServiceImage(service.name, release, order, image)

    def _relative_files(
        self,
        packages: ReleasePackages,
        folder: Path,
    ) -> Set[str]:

        return {path.relative_to(folder).as_posix() for path in packages.files(folder)}

    def _needs_build(
        self,
        packages: ReleasePackages,
        service: ServiceImage,
        docker_repository: Optional[Path],
    ) -> bool:
        """False when the last released image holds exactly the same files."""

        if docker_repository is None:

            return True

        released = docker_repository / service.name / self.IMAGE_FOLDER

        if not self.filesystem.is_directory(released):

            return True

        files = self._relative_files(packages, service.folder)

        if files != self._relative_files(packages, released):

            return True

        return any(
            self.filesystem.read_bytes(service.folder / name)
            != self.filesystem.read_bytes(released / name)
            for name in files
        )

    def _stage_service(
        self,
        packages: ReleasePackages,
        service: ServiceImage,
        output: Path,
        image_tag: str,
    ) -> Dict[str, str]:
        """Copy the image and describe it the way docker.build expects."""

        dockerfile = next(
            (
                path
                for path in self.filesystem.listdir(service.folder)
                if path.name.casefold() == self.DOCKERFILE.casefold()
                and self.filesystem.is_file(path)
            ),
            None,
        )

        if dockerfile is None:

            raise ConsolidationReleaseError(
                f"Release '{service.release}': the image of service '{service.name}' "
                f"has no {self.DOCKERFILE}.",
            )

        context = output / "services" / service.name
        destination = context / self.IMAGE_FOLDER

        for path in packages.files(service.folder):

            self.filesystem.copy(
                path,
                destination / path.relative_to(service.folder),
            )

        return {
            "dockerfile": str(destination / dockerfile.name),
            "context": str(context),
            "image_name": service.name,
            "image_tag": image_tag,
        }

    # ------------------------------------------------------------------
    # Transfers
    # ------------------------------------------------------------------

    def _collect_transfers(
        self,
        packages: ReleasePackages,
        root: Path,
        release: str,
        order: int,
        transfers: Dict[str, TransferEntry],
        warnings: List[str],
    ) -> None:
        """A later release's push replaces an earlier push to the same repository."""

        folder = packages.find_folder(
            root,
            self.SCRIPTS_LAYOUT,
            release=release,
            label="scripts/deploy",
        )

        if folder is None:

            return

        if self.filesystem.is_file(folder / self.APPLY_SCRIPT):

            warnings.append(
                f"Release '{release}': {self.APPLY_SCRIPT} is not consolidated or run; apply "
                "the YAMLs it names yourself if they are still needed.",
            )

        script = folder / self.TRANSFER_SCRIPT

        if not self.filesystem.is_file(script):

            return

        images = parse_transfer_script(
            self.filesystem.read_text(script),
            warnings,
            f"Release '{release}'",
        )

        if not images:

            warnings.append(
                f"Release '{release}': {self.TRANSFER_SCRIPT} pushes no image that can be used.",
            )

        for image in images:

            repository = image_repository(image.image)

            # Keep the releases' order in the generated script.
            transfers.pop(repository, None)

            transfers[repository] = TransferEntry(image, release, order)

    # ------------------------------------------------------------------
    # Deployments
    # ------------------------------------------------------------------

    def _load_index(
        self,
        yaml_repository: Path,
    ) -> Dict[str, Any]:

        path = yaml_repository.joinpath(*self.RESOURCE_INDEX)

        if not self.filesystem.is_file(path):

            raise ConsolidationIndexError(
                f"Resource index not found: {path}. Run oc.sync_yamls for the repository first.",
            )

        try:

            index = self.filesystem.read_json(path)

        except Exception as exc:  # noqa: BLE001 - reported with the file

            raise ConsolidationIndexError(
                f"Unable to read resource index {path}: {exc}",
            ) from exc

        if not isinstance(index, dict):

            raise ConsolidationIndexError(
                f"Resource index {path} must contain a JSON object.",
            )

        return index

    def _deployment_updates(
        self,
        services: List[ServiceImage],
        transfers: Dict[str, TransferEntry],
        index: Dict[str, Any],
        yaml_repository: Path,
        image_tag: str,
        warnings: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Image updates for oc.deployment (deployments mode). When a container gets an image
        from several releases the latest wins; within one release, the built image does.
        """

        containers = list(self._containers(index))

        # (order, built?, match, tag, transferred?)
        candidates: List[Any] = []

        for entry in transfers.values():

            match = self._match_transfer(containers, entry.image.image, warnings)

            if match is not None:

                tag = entry.image.image[len(image_repository(entry.image.image)) + 1 :]
                candidates.append((entry.order, 0, match, tag, True))

        for service in services:

            match = next(
                (
                    item
                    for item in containers
                    if image_repository(item["current_image"]) == service.name
                    or image_repository(item["current_image"]).endswith(f"/{service.name}")
                ),
                None,
            )

            if match is None:

                warnings.append(
                    f"No Deployment in the resource index uses the image '{service.name}'.",
                )

                continue

            candidates.append((service.order, 1, match, image_tag, False))

        updates: Dict[Any, Dict[str, Any]] = {}

        for _, _, match, tag, transferred in sorted(candidates, key=lambda item: item[:2]):

            current = match["current_image"].strip()

            update = {
                "name": match["deployment"],
                "kind": "Deployment",
                "action": "UPDATE",
                "file": match["file"],
                "repository": str(yaml_repository),
                "container": match["container"],
                "current_image": current,
                "target_image": f"{image_repository(current)}:{tag}",
            }

            if transferred:

                update["image_transfer"] = True

            updates[(match["deployment"], match["container"])] = update

        return list(updates.values())

    def _match_transfer(
        self,
        containers: List[Dict[str, str]],
        image: str,
        warnings: List[str],
    ) -> Optional[Dict[str, str]]:
        """By image path; else by final name when only one container uses that name."""

        repository = image_repository(image)
        path = image_path(repository)

        for item in containers:

            current = image_repository(item["current_image"])

            if current == path or current.endswith(f"/{path}"):

                return item

        name = repository.rsplit("/", 1)[-1]

        matches = [
            item
            for item in containers
            if image_repository(item["current_image"]).rsplit("/", 1)[-1] == name
        ]

        if len(matches) == 1:

            warnings.append(
                f"Image '{image}' matched Deployment '{matches[0]['deployment']}' by the name "
                f"'{name}' only; its current image is '{matches[0]['current_image']}'.",
            )

            return matches[0]

        if matches:

            warnings.append(
                f"Image '{image}' is ambiguous: several Deployments use the name '{name}' "
                "and none was updated.",
            )

        else:

            warnings.append(
                f"No Deployment in the resource index uses the image '{image}'.",
            )

        return None

    @staticmethod
    def _containers(
        index: Dict[str, Any],
    ) -> Iterator[Dict[str, str]]:
        """Every indexed Deployment container with an image."""

        deployments = index.get("deployments")

        if not isinstance(deployments, dict):

            return

        for filename, deployment in deployments.items():

            containers = deployment.get("containers") if isinstance(deployment, dict) else None

            if not isinstance(containers, dict):

                continue

            for container_name, container in containers.items():

                image = container.get("image") if isinstance(container, dict) else None

                if isinstance(image, str):

                    yield {
                        "file": filename,
                        "deployment": deployment.get("deployment"),
                        "container": container_name,
                        "current_image": image,
                    }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _result(
        self,
        *,
        success: bool,
        changed: bool,
        errors: Optional[List[Dict[str, Any]]] = None,
        warnings: Optional[List[str]] = None,
    ) -> PluginResult:

        return PluginResult(
            success=success,
            changed=changed,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=errors or [],
            warnings=warnings or [],
            metadata={
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )
