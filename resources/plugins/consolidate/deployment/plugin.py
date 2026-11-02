"""
consolidate.deployment: one set of Deployment changes for several releases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin
from lib.plugins.release_packages import (
    YAML_EXTENSIONS,
    ReleasePackages,
    natural_key,
    release_name,
)

from .consolidator import Consolidator, Source, Target
from .exceptions import (
    ConsolidationException,
    ConsolidationReleaseError,
)


class ConsolidateDeploymentPlugin(
    BasePlugin,
):
    """
    Read the Deployment changes of several release packages (standard
    `App/openshift/yamls` or App-Published `App/yamls`) and write their net
    result: one DeploymentUpdate per Deployment, for oc.deployment (folder mode)
    to apply. The YAML repository is not touched.
    """

    # Release layouts: the folder holding a release's OpenShift YAMLs.
    YAML_FOLDERS = (
        ("App", "openshift", "yamls"),
        ("App", "yamls"),
    )

    # Below the output folder, so oc.deployment does not read them as updates.
    NATIVE_FOLDER = "native"

    REPORT = "consolidation-report.json"

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
    ) -> PluginResult:
        """
        Consolidate the releases' Deployment changes.
        """

        try:

            with self.activity(
                "consolidate-deployment",
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
            Path(self.workspace) / "consolidate" / "deployment" / "releases",
            ConsolidationReleaseError,
        )

        releases = packages.resolve(
            self.arguments.path("release_directory"),
            self.arguments.list("releases"),
        )

        output = packages.prepare_output(
            self.arguments.path(
                "output_directory",
                Path(self.workspace) / "consolidated" / "deployment",
            ),
            self.arguments.boolean("overwrite", False),
        )

        names = [release_name(path) for path in releases]

        self.message.info(
            f"Consolidating Deployment changes of {len(releases)} release(s): " + ", ".join(names),
        )

        consolidator = Consolidator()
        warnings: List[str] = []

        for release in releases:

            name = release_name(release)

            yamls = packages.find_folder(
                packages.open(release),
                self.YAML_FOLDERS,
                release=name,
                label="YAML",
            )

            if yamls is None:

                warnings.append(
                    f"Release '{name}' has no App/openshift/yamls or App/yamls folder.",
                )

                continue

            for path in packages.files(yamls, YAML_EXTENSIONS):

                source = Source(
                    release=name,
                    file=path.relative_to(yamls).as_posix(),
                )

                for document in packages.yaml_documents(
                    path,
                    f"{source.release}/{source.file}",
                ):

                    consolidator.add(
                        document,
                        source,
                    )

        ordered = sorted(
            consolidator.targets,
            key=lambda item: natural_key(item.name),
        )

        for target in ordered:

            warnings.extend(
                self._native_warnings(target),
            )

        for warning in warnings:

            self.message.warning(
                warning,
            )

        targets = [self._write_target(output, target) for target in ordered]

        cancelled = {target.name: target.cancelled() for target in ordered if target.cancelled()}

        targets = [target for target in targets if target is not None]

        report = output / self.REPORT

        self.filesystem.write_json(
            report,
            {
                "releases": names,
                "targets": targets,
                "cancelled": cancelled,
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
                "releases": names,
                "targets": targets,
                "changed": bool(targets),
            },
        )

        if targets:

            self.message.success(
                f"Consolidated {len(targets)} Deployment(s) into {output}.",
            )

        else:

            self.message.info(
                "No release changes a Deployment.",
            )

        return self._result(
            success=True,
            changed=bool(targets),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _write_target(
        self,
        output: Path,
        target: Target,
    ) -> Optional[Dict[str, Any]]:

        document = target.document()

        if document is None and target.native is None:

            return None

        path = None

        if document is not None:

            path = output / f"deployment-{target.name}.yaml"

            self.filesystem.write_text(
                path,
                self.filesystem.serialize_yaml_documents(
                    [document],
                ),
            )

        native_path = None

        if target.native is not None:

            native_path = output / self.NATIVE_FOLDER / f"deployment-{target.name}.yaml"

            self.filesystem.mkdir(
                native_path.parent,
            )

            self.filesystem.write_text(
                native_path,
                self.filesystem.serialize_yaml_documents(
                    [target.native],
                ),
            )

        return {
            "kind": "Deployment",
            "name": target.name,
            "file": str(path) if path else None,
            "native_file": str(native_path) if native_path else None,
            "releases": list(dict.fromkeys(source.release for source in target.sources)),
            "sources": [
                {"release": source.release, "file": source.file} for source in target.sources
            ],
            # The release that last changed each item.
            "keys": target.keys(),
        }

    @staticmethod
    def _native_warnings(
        target: Target,
    ) -> List[str]:
        """What a person has to do or check for a complete Deployment resource."""

        if target.native is None:

            return []

        warnings = [
            f"Deployment '{target.name}': oc.deployment (folder mode) does not create "
            f"resources; if the YAML repository lacks it, add "
            f"{ConsolidateDeploymentPlugin.NATIVE_FOLDER}/deployment-{target.name}.yaml "
            "there first.",
        ]

        if len(target.native_releases) > 1:

            warnings.append(
                f"Deployment '{target.name}': complete resources in "
                f"{', '.join(target.native_releases)}; only the one of "
                f"{target.native_releases[-1]} is kept.",
            )

        if target.document() is not None:

            warnings.append(
                f"Deployment '{target.name}' has a complete resource and updates: the updates "
                "are applied to whatever the YAML repository holds, so check that they still "
                "fit the complete resource.",
            )

        return warnings

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
