"""
consolidate.cm_secret: one set of ConfigMap/Secret changes for several releases.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .consolidator import Consolidator, Source, Target
from .exceptions import (
    ConsolidationException,
    ConsolidationReleaseError,
)


def natural_key(text: str) -> List[Any]:
    """Sort key that orders numbers by value: H9 < H10 < H101."""

    return [
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", text)
        if part
    ]


class ConsolidateCmSecretPlugin(
    BasePlugin,
):
    """
    Read the ConfigMap/Secret changes of several release packages (standard
    `App/openshift/yamls` or App-Published `App/yamls`) and write their net
    result: one YAML per ConfigMap/Secret, for oc.cm_secret_update (folder
    mode) to apply. The YAML repository is not touched.
    """

    # Release layouts: the folder holding a release's OpenShift YAMLs.
    YAML_FOLDERS = (
        ("App", "openshift", "yamls"),
        ("App", "yamls"),
    )

    ARCHIVES = (
        ".zip",
        ".tar",
        ".tgz",
        ".gz",
    )

    YAML_EXTENSIONS = (
        ".yaml",
        ".yml",
    )

    IGNORED = (
        "__MACOSX",
        ".DS_Store",
    )

    REPORT = "consolidation-report.json"

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
    ) -> PluginResult:
        """
        Consolidate the releases' ConfigMap/Secret changes.
        """

        try:

            with self.activity(
                "consolidate-cm-secret",
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
                    str(exc),
                ],
            )

    def _execute(
        self,
    ) -> PluginResult:

        releases = self._releases()

        output = self._output_directory()

        self.message.info(
            f"Consolidating ConfigMap/Secret changes of {len(releases)} release(s): "
            + ", ".join(self._release_name(path) for path in releases),
        )

        consolidator = Consolidator()
        warnings: List[str] = []

        for release in releases:

            name = self._release_name(release)
            yamls = self._yaml_folder(self._open(release, name), name)

            if yamls is None:

                warnings.append(
                    f"Release '{name}' has no App/openshift/yamls or App/yamls folder.",
                )

                continue

            for path in self._yaml_files(yamls):

                source = Source(
                    release=name,
                    file=path.relative_to(yamls).as_posix(),
                )

                for document in self._documents(path, source):

                    consolidator.add(
                        document,
                        source,
                    )

        for warning in warnings:

            self.message.warning(
                warning,
            )

        targets = [
            self._write_target(output, target)
            for target in sorted(
                consolidator.targets,
                key=lambda item: (item.kind, natural_key(item.name)),
            )
        ]
        targets = [target for target in targets if target is not None]

        report = output / self.REPORT

        self.filesystem.write_json(
            report,
            {
                "releases": [self._release_name(path) for path in releases],
                "targets": targets,
                "ignored_documents": consolidator.ignored,
                "warnings": warnings,
            },
            indent=2,
            sort_keys=False,
        )

        self.artifacts["consolidation_report"] = report

        self.outputs.update(
            {
                "output_directory": str(output),
                "report": str(report),
                "releases": [self._release_name(path) for path in releases],
                "targets": targets,
                "changed": bool(targets),
            },
        )

        if targets:

            self.message.success(
                f"Consolidated {len(targets)} ConfigMap/Secret(s) into {output}.",
            )

        else:

            self.message.info(
                "No release changes a ConfigMap or Secret.",
            )

        return self._result(
            success=True,
            changed=bool(targets),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Releases
    # ------------------------------------------------------------------

    def _releases(
        self,
    ) -> List[Path]:
        """
        The releases in the order they are applied: the given list as is,
        or the folder's packages in natural name order.
        """

        folder = self.arguments.path(
            "release_directory",
        )

        listed = self.arguments.list(
            "releases",
        )

        if (folder is None) == (not listed):

            raise ConsolidationReleaseError(
                "Give either 'release_directory' or 'releases' (one of them, not both).",
            )

        if listed:

            releases = [Path(str(item)).expanduser() for item in listed]

            for release in releases:

                if not self.filesystem.exists(release):

                    raise ConsolidationReleaseError(
                        f"Release not found: {release}",
                    )

            if len({self._release_name(path) for path in releases}) != len(releases):

                raise ConsolidationReleaseError(
                    "Two releases have the same name: " + ", ".join(map(str, releases)),
                )

            return releases

        assert folder is not None

        if not self.filesystem.is_directory(folder):

            raise ConsolidationReleaseError(
                f"Release folder not found: {folder}",
            )

        releases = [
            path
            for path in self.filesystem.listdir(folder)
            if path.name not in self.IGNORED
            and not path.name.startswith(".")
            and (self.filesystem.is_directory(path) or self._is_archive(path))
        ]

        if not releases:

            raise ConsolidationReleaseError(
                f"No release packages (ZIPs or folders) in {folder}.",
            )

        names = [self._release_name(path) for path in releases]

        duplicates = sorted({name for name in names if names.count(name) > 1})

        if duplicates:

            raise ConsolidationReleaseError(
                "Release given both as a ZIP and a folder: " + ", ".join(duplicates),
            )

        return sorted(
            releases,
            key=lambda path: natural_key(self._release_name(path)),
        )

    def _open(
        self,
        release: Path,
        name: str,
    ) -> Path:
        """A release folder; archives are extracted into the run workspace."""

        if self.filesystem.is_directory(release):

            return release

        if not self._is_archive(release):

            raise ConsolidationReleaseError(
                f"Release '{release}' is neither a folder nor an archive.",
            )

        destination = Path(self.workspace) / "consolidate" / "cm_secret" / "releases" / name

        if self.filesystem.exists(destination):

            self.filesystem.remove(
                destination,
            )

        try:

            return Path(
                self.archive.extract(
                    release,
                    destination,
                ),
            )

        except Exception as exc:  # noqa: BLE001 - reported as a release error

            raise ConsolidationReleaseError(
                f"Unable to extract release '{release}': {exc}",
            ) from exc

    def _yaml_folder(
        self,
        root: Path,
        name: str,
    ) -> Optional[Path]:
        """
        The release's OpenShift YAML folder: at the top, or inside the one
        folder the package holds (H010/..., App-Published/...).
        """

        candidates = [root] + [
            path
            for path in self.filesystem.listdir(root)
            if self.filesystem.is_directory(path)
            and path.name not in self.IGNORED
            and not path.name.startswith(".")
        ]

        found = []

        for candidate in candidates:

            for parts in self.YAML_FOLDERS:

                folder = candidate.joinpath(*parts)

                if self.filesystem.is_directory(folder):

                    found.append(folder)

                    break

        if len(found) > 1:

            raise ConsolidationReleaseError(
                f"Release '{name}' has several YAML folders: "
                + ", ".join(str(path) for path in found),
            )

        return found[0] if found else None

    def _yaml_files(
        self,
        folder: Path,
    ) -> List[Path]:
        """YAML files below the folder, in natural path order."""

        return sorted(
            (
                path
                for path in self.filesystem.find(folder, "*", recursive=True)
                if self.filesystem.is_file(path)
                and path.suffix.casefold() in self.YAML_EXTENSIONS
                and not any(part in self.IGNORED for part in path.parts)
                and not path.name.startswith("._")
            ),
            key=lambda path: natural_key(path.relative_to(folder).as_posix()),
        )

    def _documents(
        self,
        path: Path,
        source: Source,
    ) -> List[Any]:

        try:

            return [
                document
                for document in self.filesystem.load_yaml_documents(
                    self.filesystem.read_text(path),
                )
                if document is not None
            ]

        except Exception as exc:  # noqa: BLE001 - reported with the file
            raise ConsolidationReleaseError(
                f"{source.release}/{source.file} is not valid YAML: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _output_directory(
        self,
    ) -> Path:
        """An empty output folder (emptied first when `overwrite`)."""

        output = self.arguments.path(
            "output_directory",
            Path(self.workspace) / "consolidated" / "cm_secret",
        )

        assert output is not None

        if self.filesystem.exists(output):

            if not self.filesystem.is_directory(output):

                raise ConsolidationReleaseError(
                    f"output_directory is not a folder: {output}",
                )

            if self.filesystem.listdir(output):

                if not self.arguments.boolean("overwrite", False):

                    raise ConsolidationReleaseError(
                        f"output_directory is not empty: {output}. Set 'overwrite' to "
                        "empty it first (old YAMLs there would be applied too).",
                    )

                self.filesystem.remove(
                    output,
                )

        self.filesystem.mkdir(
            output,
        )

        return output

    def _write_target(
        self,
        output: Path,
        target: Target,
    ) -> Optional[Dict[str, Any]]:

        documents = target.documents()

        if not documents:

            return None

        path = output / f"{target.kind.lower()}-{target.name}.yaml"

        self.filesystem.write_text(
            path,
            self.filesystem.serialize_yaml_documents(
                documents,
            ),
        )

        return {
            "kind": target.kind,
            "name": target.name,
            "file": str(path),
            "releases": list(dict.fromkeys(source.release for source in target.sources)),
            "sources": [
                {"release": source.release, "file": source.file} for source in target.sources
            ],
            # The release that last changed each key.
            "keys": dict(target.last_changed),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_archive(
        self,
        path: Path,
    ) -> bool:

        return self.filesystem.is_file(path) and path.suffix.casefold() in self.ARCHIVES

    @staticmethod
    def _release_name(
        path: Path,
    ) -> str:
        """H010.zip, H010.tar.gz and the folder H010 are all 'H010'."""

        name = path.name
        for suffix in (".tar.gz", ".tgz", ".tar", ".zip"):
            if name.casefold().endswith(suffix):
                return name[: -len(suffix)]
        return name

    def _result(
        self,
        *,
        success: bool,
        changed: bool,
        errors: Optional[List[str]] = None,
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
