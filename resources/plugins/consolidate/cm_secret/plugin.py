"""
consolidate.cm_secret: one set of ConfigMap/Secret changes for several releases.
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

        packages = ReleasePackages(
            self.filesystem,
            self.archive,
            Path(self.workspace) / "consolidate" / "cm_secret" / "releases",
            ConsolidationReleaseError,
        )

        releases = packages.resolve(
            self.arguments.path("release_directory"),
            self.arguments.list("releases"),
        )

        output = packages.prepare_output(
            self.arguments.path(
                "output_directory",
                Path(self.workspace) / "consolidated" / "cm_secret",
            ),
            self.arguments.boolean("overwrite", False),
        )

        self.message.info(
            f"Consolidating ConfigMap/Secret changes of {len(releases)} release(s): "
            + ", ".join(release_name(path) for path in releases),
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
                "releases": [release_name(path) for path in releases],
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
                "releases": [release_name(path) for path in releases],
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
    # Output
    # ------------------------------------------------------------------

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
