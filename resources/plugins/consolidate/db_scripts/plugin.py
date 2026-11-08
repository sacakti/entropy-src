"""
consolidate.db_scripts: one execution plan for the database scripts of several releases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin
from lib.plugins.release_packages import (
    ReleasePackages,
    release_name,
)

from .exceptions import (
    ConsolidationException,
    ConsolidationReleaseError,
)
from .planner import Entry, Plan, parse_plan


class ConsolidateDbScriptsPlugin(
    BasePlugin,
):
    """
    Collect the database scripts of several release packages into one package
    whose execution plan runs them all, release by release, for sqlplus.generic
    (plan mode). Scripts are copied unchanged and nothing is run here.
    """

    DATABASE_FOLDER = "DBScripts"

    # Same names, in the same order, as release.context_builder looks for.
    PLAN_NAMES = (
        "execution_plan.yaml",
        "execution_plan.yml",
        "execution_plan.json",
    )

    # Left behind by earlier runs; sqlplus.generic creates them again.
    GENERATED = (".entropy",)

    REPORT = "consolidation-report.json"

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
    ) -> PluginResult:
        """
        Consolidate the releases' database scripts.
        """

        try:

            with self.activity(
                "consolidate-db-scripts",
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
            Path(self.workspace) / "consolidate" / "db_scripts" / "releases",
            ConsolidationReleaseError,
        )

        releases = packages.resolve(
            self.arguments.path("release_directory"),
            self.arguments.list("releases"),
        )

        output = packages.prepare_output(
            self.arguments.path(
                "output_directory",
                Path(self.workspace) / "consolidated" / "db_scripts",
            ),
            self.arguments.boolean("overwrite", False),
        )

        names = [release_name(path) for path in releases]

        self.message.info(
            f"Consolidating database scripts of {len(releases)} release(s): " + ", ".join(names),
        )

        database = output / self.DATABASE_FOLDER

        plan = Plan()
        warnings: List[str] = []

        for release in releases:

            name = release_name(release)

            folder = packages.find_folder(
                packages.open(release),
                ((self.DATABASE_FOLDER,),),
                release=name,
                label=self.DATABASE_FOLDER,
            )

            if folder is None:

                continue

            for entry in self._release_entries(packages, folder, name, warnings):

                self._copy_application(
                    packages,
                    folder / entry.source_application,
                    database / entry.application,
                )

                plan.add(
                    entry,
                )

        for warning in warnings:

            self.message.warning(
                warning,
            )

        scripts: List[Dict[str, str]] = []

        if plan.entries:

            self.filesystem.write_yaml(
                database / self.PLAN_NAMES[0],
                plan.document(),
            )

            scripts = [
                {
                    "application": path.parent.name,
                    "directory": path.parent.relative_to(database).as_posix(),
                    "script": str(path),
                }
                for path in packages.files(database, (".sql",))
            ]

        steps = [entry.report() for entry in plan.entries]

        report = output / self.REPORT

        self.filesystem.write_json(
            report,
            {
                "releases": names,
                "steps": steps,
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
                "steps": steps,
                # The shape of release.context_builder's 'database' output.
                "database": {
                    "dir": str(database) if plan.entries else None,
                    "scripts": scripts,
                    "execution_plan": plan.document() if plan.entries else None,
                },
                "changed": bool(steps),
            },
        )

        if steps:

            self.message.success(
                f"Consolidated {len(steps)} database execution(s) into {database}.",
            )

        else:

            self.message.info(
                "No release has database scripts to run.",
            )

        return self._result(
            success=True,
            changed=bool(steps),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Release
    # ------------------------------------------------------------------

    def _release_entries(
        self,
        packages: ReleasePackages,
        folder: Path,
        release: str,
        warnings: List[str],
    ) -> List[Entry]:
        """The executions a release asks for; what it holds but never runs is reported."""

        plan_file = next(
            (
                folder / name
                for name in self.PLAN_NAMES
                if self.filesystem.is_file(
                    folder / name,
                )
            ),
            None,
        )

        if plan_file is None:

            if packages.files(folder, (".sql",)):

                warnings.append(
                    f"Release '{release}' has database scripts but no execution plan; "
                    "they are not included, as sqlplus.generic would not run them.",
                )

            return []

        entries = parse_plan(
            self._read_plan(plan_file, release),
            release,
        )

        for application in self._unplanned_folders(
            folder,
            {entry.source_application for entry in entries},
        ):

            warnings.append(
                f"Release '{release}': {self.DATABASE_FOLDER}/{application} is not in the "
                "execution plan; it is not included, as sqlplus.generic would not run it.",
            )

        for entry in entries:

            script = folder / entry.source_application / entry.calling_script

            if not self.filesystem.is_file(script):

                raise ConsolidationReleaseError(
                    f"Release '{release}': calling script '{entry.calling_script}' of "
                    f"application '{entry.source_application}' was not found in "
                    f"{self.DATABASE_FOLDER}/{entry.source_application}.",
                )

            if not self.filesystem.read_text(script).strip():

                warnings.append(
                    f"Release '{release}': calling script '{entry.calling_script}' of "
                    f"application '{entry.source_application}' is empty.",
                )

        return entries

    def _unplanned_folders(
        self,
        folder: Path,
        planned: Set[str],
        prefix: str = "",
    ) -> List[str]:
        """
        Folders under DBScripts the plan never reaches. A group folder (H01 for
        a planned 'H01/App1') is looked into rather than reported.
        """

        unplanned: List[str] = []

        for path in self.filesystem.listdir(folder):

            if not self.filesystem.is_directory(path) or path.name.startswith((".", "__MACOSX")):
                continue

            name = f"{prefix}{path.name}"

            if name in planned:
                continue

            if any(application.startswith(f"{name}/") for application in planned):

                unplanned.extend(
                    self._unplanned_folders(
                        path,
                        planned,
                        f"{name}/",
                    )
                )

                continue

            unplanned.append(
                name,
            )

        return unplanned

    def _read_plan(
        self,
        path: Path,
        release: str,
    ) -> Any:

        try:

            if path.suffix.casefold() == ".json":

                return self.filesystem.read_json(path)

            return self.filesystem.read_yaml(path)

        except Exception as exc:  # noqa: BLE001 - reported with the file

            raise ConsolidationReleaseError(
                f"Release '{release}': {path.name} is not valid: {exc}",
            ) from exc

    def _copy_application(
        self,
        packages: ReleasePackages,
        source: Path,
        destination: Path,
    ) -> None:
        """Copy an application's files unchanged, so relative paths inside still work."""

        for path in packages.files(source):

            relative = path.relative_to(source)

            if any(part in self.GENERATED for part in relative.parts):

                continue

            self.filesystem.copy(
                path,
                destination / relative,
            )

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
