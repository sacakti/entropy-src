"""
Extension manager: Python libraries for plugins, several versions side by
side (see lib.extensions.packages for the layout and
lib.extensions.resolver for how plugins get them).
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from packaging.utils import canonicalize_name

from core.context import EntropyContext
from lib.extensions import packages
from lib.extensions.resolver import activate, resolve
from lib.extensions.store import ExtensionStore

from .exceptions import (
    ExtensionExistsError,
    ExtensionInstallationError,
    ExtensionNotFoundError,
    ExtensionValueError,
)

# One pip at a time: installs share the staging area and the index.
_LOCK = threading.Lock()


class ExtensionManager:
    """Install, list, check and remove extension versions."""

    def __init__(self, context: EntropyContext) -> None:
        assert context.paths is not None
        assert context.database_manager is not None
        self._context = context
        self._paths = context.paths
        self.store = ExtensionStore(context.database_manager.connection)
        self._events = (
            context.observability.emitter("extensions") if context.observability else None
        )

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    @property
    def libraries(self) -> Path:
        return self._paths.extensions.root / "libs"

    def folder(self, name: str, version: str) -> Path:
        return self.libraries / canonicalize_name(name) / version

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list(self) -> List[Dict[str, Any]]:
        return self.store.list()

    def exists(self, name: str) -> bool:
        return bool(self.store.versions(name))

    def builtin(self) -> List[Dict[str, str]]:
        """The libraries Entropy itself runs with."""

        from importlib import metadata

        seen: Dict[str, Dict[str, str]] = {}
        for distribution in metadata.distributions():
            name = distribution.metadata.get("Name")
            if name and canonicalize_name(name) not in seen:
                seen[canonicalize_name(name)] = {
                    "name": name,
                    "version": distribution.version,
                    "summary": distribution.metadata.get("Summary") or "",
                }
        return sorted(seen.values(), key=lambda entry: entry["name"].lower())

    def check(self, requirements: Iterable[Any]) -> List[Dict[str, Any]]:
        return resolve(requirements, self.store.list(), packages.host_distributions())

    def missing(self, requirements: Iterable[Any]) -> List[Dict[str, Any]]:
        return [entry for entry in self.check(requirements) if entry["status"] == "missing"]

    def activate(self, requirements: Iterable[Any]) -> List[str]:
        """Put the versions these requirements need on this process's import path."""

        resolved = self.check(requirements)
        missing = [entry["requirement"] for entry in resolved if entry["status"] == "missing"]
        if missing:
            raise ExtensionNotFoundError(", ".join(missing))
        return activate(resolved, self.libraries)

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def install(
        self,
        name: str,
        version: Optional[str] = None,
        *,
        dependencies: bool = True,
        index_url: Optional[str] = None,
        user: str = "",
    ) -> Dict[str, Any]:
        """Install a library from the package index (PyPI or the configured one)."""

        from lib.extensions.resolver import requirement_text

        name = packages.check_name(name)
        requirement = requirement_text(name, version)
        self._refuse_known(name, version)
        with _LOCK:
            staging = self._staging()
            try:
                packages.build_wheels(
                    requirement,
                    staging / "wheels",
                    dependencies=dependencies,
                    index_url=index_url,
                )
                project, found, _ = packages.main_wheel(staging / "wheels", name)
                return self._finish(
                    staging,
                    project,
                    found,
                    source="index",
                    origin=index_url or "default index",
                    dependencies=dependencies,
                    user=user,
                )
            finally:
                packages.remove_tree(staging)

    def install_upload(
        self,
        filename: str,
        data: bytes,
        *,
        name: Optional[str] = None,
        version: Optional[str] = None,
        summary: str = "",
        dependencies: bool = True,
        index_url: Optional[str] = None,
        user: str = "",
    ) -> Dict[str, Any]:
        """
        Install an uploaded library: a wheel, a source archive (pip builds
        it), or a plain .py module / zipped package folder (name and version
        given here).
        """

        filename = Path(filename or "").name
        lower = filename.lower()
        if not (lower.endswith(packages.PIP_ARCHIVES) or lower.endswith(".py")):
            raise ExtensionValueError(
                "Upload a wheel (.whl), a source archive (.tar.gz, .zip), a module (.py) or a "
                "zipped package folder (.zip)."
            )
        with _LOCK:
            staging = self._staging()
            try:
                wheels = staging / "wheels"
                bundle = packages.bundled_wheels(lower, data)
                if bundle:
                    # A .zip of wheels: the library and its dependencies,
                    # downloaded elsewhere; nothing is fetched or built.
                    packages.select_wheels(bundle, wheels)
                    project = packages.main_project(wheels, name)
                    _, found, _ = packages.main_wheel(wheels, project)
                    self._refuse_known(project, f"=={found}")
                    missing = packages.missing_requirements(wheels, packages.host_distributions())
                    if missing:
                        raise ExtensionValueError(
                            "The zip lacks dependencies: "
                            + "; ".join(missing)
                            + ". Add their wheels (pip download fetches them all) and upload again."
                        )
                    dependencies = True
                elif packages.is_plain(lower, data):
                    if not name or not version:
                        raise ExtensionValueError(
                            "This file has no package information: give it a name and version."
                        )
                    wheel = packages.make_wheel(lower, data, name, version, summary, wheels)
                    project, found = packages.wheel_identity(wheel)
                    self._refuse_known(project, f"=={found}")
                    dependencies = False
                else:
                    upload = staging / "upload" / filename
                    upload.parent.mkdir(parents=True)
                    upload.write_bytes(data)
                    if lower.endswith(".whl"):
                        project, found = packages.wheel_identity(upload)
                        self._refuse_known(project, f"=={found}")
                    if lower.endswith(".whl") and not dependencies:
                        # Nothing to resolve or build: use the wheel as it is.
                        wheels.mkdir(parents=True)
                        (wheels / filename).write_bytes(data)
                    else:
                        packages.build_wheels(
                            str(upload), wheels, dependencies=dependencies, index_url=index_url
                        )
                    project, found = self._uploaded_identity(wheels, upload, name)
                    self._refuse_known(project, f"=={found}")
                return self._finish(
                    staging,
                    project,
                    found,
                    source="upload",
                    origin=filename,
                    dependencies=dependencies,
                    user=user,
                    summary=summary,
                )
            finally:
                packages.remove_tree(staging)

    def install_bundle(
        self, name: str, version: Optional[str], data: bytes, user: str = "node"
    ) -> Dict[str, Any]:
        """Install a version from another Entropy's wheels (nodes, from the server)."""

        existing = self.store.get(name, version) if version else None
        if existing:
            return existing
        with _LOCK:
            staging = self._staging()
            try:
                packages.unpack_wheels(data, staging / "wheels")
                project, found, _ = packages.main_wheel(staging / "wheels", name)
                existing = self.store.get(project, found)
                if existing:
                    return existing
                return self._finish(
                    staging,
                    project,
                    found,
                    source="server",
                    origin="Entropy server",
                    dependencies=True,
                    user=user,
                )
            finally:
                packages.remove_tree(staging)

    def bundle(self, name: str, version: str) -> bytes:
        if not self.store.get(name, version):
            raise ExtensionNotFoundError(f"{name} {version}")
        return packages.pack_wheels(self.folder(name, version) / "wheels")

    # ------------------------------------------------------------------
    # Removal and checks
    # ------------------------------------------------------------------

    def uninstall(self, name: str, version: Optional[str] = None) -> List[str]:
        versions = [entry["version"] for entry in self.store.versions(name)]
        if not versions:
            raise ExtensionNotFoundError(name)
        if version is None:
            if len(versions) > 1:
                raise ExtensionValueError(
                    f"{name} has versions {', '.join(versions)}: say which one to remove."
                )
            version = versions[0]
        if version not in versions:
            raise ExtensionNotFoundError(f"{name} {version}")
        packages.remove_tree(self.folder(name, version))
        self.store.remove(name, version)
        self._log("success", f"Extension {name} {version} removed.")
        return [version]

    def verify(self, name: str, version: str) -> List[str]:
        """Problems with an installed version (empty when it is fine)."""

        entry = self.store.get(name, version)
        if entry is None:
            raise ExtensionNotFoundError(f"{name} {version}")
        folder = self.folder(name, version)
        problems = []
        if not (folder / "site").is_dir():
            problems.append("The installed files are missing.")
        if not any((folder / "wheels").glob("*.whl")):
            problems.append("The wheels are missing; nodes cannot install this version.")
        installed = {
            canonicalize_name(dist["name"]) for dist in packages.distributions(folder / "site")
        }
        if canonicalize_name(name) not in installed:
            problems.append(f"{name} itself is not installed in its folder.")
        return problems

    def repair(self, name: str, version: str) -> Dict[str, Any]:
        """Reinstall a version from its kept wheels."""

        entry = self.store.get(name, version)
        if entry is None:
            raise ExtensionNotFoundError(f"{name} {version}")
        folder = self.folder(name, version)
        if not any((folder / "wheels").glob("*.whl")):
            raise ExtensionInstallationError("Its wheels are gone: remove it and install it again.")
        with _LOCK:
            packages.remove_tree(folder / "site")
            packages.install(folder / "wheels", folder / "site")
            packages.prune(folder / "site", entry["name"], packages.host_distributions())
        return entry

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _staging(self) -> Path:
        staging = self.libraries / ".staging" / uuid.uuid4().hex
        staging.mkdir(parents=True)
        return staging

    def _refuse_known(self, name: str, version: Optional[str]) -> None:
        """Refuse a library version Entropy or an extension already has."""

        from lib.extensions.resolver import fits, specifier

        exact = str(specifier(version))
        if not exact.startswith("=="):
            return  # a range: the version is known once pip resolved it
        wanted = exact[2:]
        host = packages.host_distributions()
        canonical = canonicalize_name(name)
        if canonical in host and fits(host[canonical], specifier(wanted)):
            raise ExtensionExistsError(
                f"{name} {host[canonical]} is already part of Entropy: plugins can use it as it "
                "is. Install a different version only if a plugin needs one."
            )
        for entry in self.store.versions(name):
            if fits(entry["version"], specifier(wanted)):
                raise ExtensionExistsError(f"{name} {entry['version']} is already installed.")

    @staticmethod
    def _uploaded_identity(wheels: Path, upload: Path, name: Optional[str]):
        if upload.name.lower().endswith(".whl"):
            return packages.wheel_identity(upload)
        # A source archive: its wheel is the one not built for a dependency.
        built = sorted(wheels.glob("*.whl"), key=lambda path: path.stat().st_mtime)
        if name:
            project, found, _ = packages.main_wheel(wheels, name)
            return project, found
        stem = upload.name.lower()
        for wheel in built:
            project, found = packages.wheel_identity(wheel)
            if canonicalize_name(project) in canonicalize_name(stem.replace(".tar.gz", "")):
                return project, found
        if len(built) == 1:
            return packages.wheel_identity(built[0])
        raise ExtensionValueError("Cannot tell which library the archive holds: give its name.")

    def _finish(
        self,
        staging: Path,
        name: str,
        version: str,
        *,
        source: str,
        origin: str,
        dependencies: bool,
        user: str,
        summary: str = "",
    ) -> Dict[str, Any]:
        self._refuse_known(name, f"=={version}")
        site = staging / "site"
        packages.install(staging / "wheels", site)
        shared = packages.prune(site, name, packages.host_distributions())
        installed = packages.distributions(site)
        main = next(
            (
                dist
                for dist in installed
                if canonicalize_name(dist["name"]) == canonicalize_name(name)
            ),
            None,
        )
        target = self.folder(name, version)
        target.parent.mkdir(parents=True, exist_ok=True)
        packages.remove_tree(target)
        target.mkdir()
        (staging / "wheels").rename(target / "wheels")
        site.rename(target / "site")
        entry = self.store.add(
            name=main["name"] if main else name,
            version=version,
            source=source,
            origin=origin,
            summary=summary or (main["summary"] if main else ""),
            packages=packages.names(installed),
            shared=shared,
            size=packages.folder_size(target),
            installed_by=user,
        )
        self._log("success", f"Extension {entry['name']} {version} installed.")
        return entry

    def _log(self, level: str, message: str) -> None:
        if self._events is not None:
            getattr(self._events.log, level, self._events.log.info)(message)
