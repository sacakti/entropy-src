"""
Building and installing extension packages with pip.

Every installed version lives in its own folder:

    extensions/libs/<canonical name>/<version>/
        wheels/   the wheels it was installed from (the library and its
                  dependencies), kept so nodes can install the same files
        site/     pip --target folder put on a plugin's import path

Dependencies that Entropy itself already has at the very same version are
removed from `site/`: the plugin uses Entropy's copy.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from packaging.utils import canonicalize_name, parse_wheel_filename

from lib.extensions.exceptions import ExtensionInstallationError, ExtensionValueError

PIP_TIMEOUT = 900
NAME_PATTERN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
# Uploads that pip builds itself (they carry their own metadata).
PIP_ARCHIVES = (".whl", ".tar.gz", ".tgz", ".zip")


def check_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_PATTERN.match(name) or len(name) > 120:
        raise ExtensionValueError(
            "A library name has letters, digits, '.', '-' and '_' only (like 'requests')."
        )
    return name


def check_version(version: str) -> str:
    from packaging.version import InvalidVersion, Version

    try:
        return str(Version((version or "").strip()))
    except InvalidVersion:
        raise ExtensionValueError(f"'{version}' is not a valid version (like 1.0.2).") from None


def _pip(arguments: List[str], index_url: Optional[str] = None) -> str:
    command = [sys.executable, "-m", "pip", *arguments, "--disable-pip-version-check", "--no-input"]
    if index_url:
        command += ["--index-url", index_url]
    environment = {**os.environ, "PIP_NO_INPUT": "1"}
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=PIP_TIMEOUT,
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ExtensionInstallationError("pip did not finish within 15 minutes.") from None
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip().splitlines()
        # The last lines say what went wrong; the rest is pip's progress.
        raise ExtensionInstallationError("\n".join(output[-12:]) or "pip failed.")
    return result.stdout


def build_wheels(
    requirement: str,
    wheels: Path,
    *,
    dependencies: bool = True,
    index_url: Optional[str] = None,
    offline: bool = False,
) -> None:
    """Wheels for a requirement ('name==1.0', 'name>=2', or a local file) and its dependencies."""

    wheels.mkdir(parents=True, exist_ok=True)
    if not pip_available():
        raise ExtensionInstallationError(
            "Entropy's Python has no pip, so it cannot fetch libraries or build source "
            "archives. Upload wheels instead (without dependencies), or install pip into "
            "Entropy's Python."
        )
    arguments = ["wheel", "--wheel-dir", str(wheels)]
    if not dependencies:
        arguments.append("--no-deps")
    if offline:
        arguments += ["--no-index", "--find-links", str(wheels)]
    _pip([*arguments, requirement], None if offline else index_url)


def main_wheel(wheels: Path, name: str) -> Tuple[str, str, Path]:
    """(project name, version, file) of `name`'s wheel among `wheels`."""

    wanted = canonicalize_name(name)
    found = []
    for wheel in wheels.glob("*.whl"):
        try:
            project, version, _, _ = parse_wheel_filename(wheel.name)
        except Exception:
            continue
        if canonicalize_name(project) == wanted:
            found.append((str(project), str(version), wheel))
    if not found:
        raise ExtensionInstallationError(f"pip produced no wheel for '{name}'.")
    from packaging.version import Version

    return max(found, key=lambda entry: Version(entry[1]))


def wheel_identity(wheel: Path) -> Tuple[str, str]:
    project, version, _, _ = parse_wheel_filename(wheel.name)
    return str(project), str(version)


def install(wheels: Path, site: Path) -> None:
    """
    Unpack every wheel in `wheels` into `site`. `wheels` holds exactly what
    pip resolved (the library and its dependencies), so this needs no pip
    and gives the server and every node the very same files.
    """

    site.mkdir(parents=True, exist_ok=True)
    root = site.resolve()
    for wheel in sorted(wheels.glob("*.whl")):
        try:
            archive = zipfile.ZipFile(wheel)
        except zipfile.BadZipFile:
            raise ExtensionInstallationError(f"{wheel.name} is not a valid wheel.") from None
        with archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                parts = [part for part in name.split("/") if part]
                if not parts or ".." in parts or name.startswith("/"):
                    raise ExtensionInstallationError(f"{wheel.name} has an unsafe entry.")
                # name-1.0.data/purelib|platlib/... belongs in site; scripts,
                # headers and data files are not needed to import the library.
                if parts[0].endswith(".data"):
                    if len(parts) < 3 or parts[1] not in ("purelib", "platlib"):
                        continue
                    parts = parts[2:]
                target = (site / "/".join(parts)).resolve()
                if not str(target).startswith(str(root)):
                    raise ExtensionInstallationError(f"{wheel.name} has an unsafe entry.")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))


def pip_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("pip") is not None


# ----------------------------------------------------------------------
# What is installed
# ----------------------------------------------------------------------


def _metadata(dist_info: Path) -> Tuple[str, str, str]:
    try:
        message = Parser().parsestr((dist_info / "METADATA").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return "", "", ""
    return message.get("Name") or "", message.get("Version") or "", message.get("Summary") or ""


def distributions(site: Path) -> List[Dict[str, str]]:
    """Distributions installed in a --target folder."""

    found = []
    for dist_info in sorted(site.glob("*.dist-info")):
        name, version, summary = _metadata(dist_info)
        if name:
            found.append(
                {"name": name, "version": version, "summary": summary, "dist_info": dist_info.name}
            )
    return found


def host_distributions() -> Dict[str, str]:
    """Libraries Entropy itself runs with: canonical name -> version."""

    from importlib import metadata

    found: Dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            found.setdefault(canonicalize_name(name), distribution.version)
    return found


def _record(site: Path, dist_info: str) -> List[Path]:
    record = site / dist_info / "RECORD"
    files = []
    if record.is_file():
        with record.open(newline="", encoding="utf-8") as stream:
            for row in csv.reader(stream):
                if row:
                    files.append((site / row[0]).resolve())
    return files


def prune(site: Path, keep: str, host: Dict[str, str]) -> List[str]:
    """
    Remove dependencies identical to Entropy's own (same name and version),
    except the library itself; returns what was removed.
    """

    keep = canonicalize_name(keep)
    removed = []
    root = site.resolve()
    for distribution in distributions(site):
        canonical = canonicalize_name(distribution["name"])
        if canonical == keep or host.get(canonical) != distribution["version"]:
            continue
        for path in _record(site, distribution["dist_info"]):
            if str(path).startswith(str(root)) and path.is_file():
                path.unlink()
        shutil.rmtree(site / distribution["dist_info"], ignore_errors=True)
        removed.append(f"{distribution['name']}=={distribution['version']}")
    # Folders the removed files leave empty.
    for directory in sorted(site.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return removed


def folder_size(path: Path) -> int:
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


# ----------------------------------------------------------------------
# Plain modules and packages (no packaging metadata)
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# Wheel bundles: a .zip of wheels (e.g. from `pip download`), for servers
# without access to a package index
# ----------------------------------------------------------------------


def bundled_wheels(filename: str, data: bytes) -> List[Tuple[str, bytes]]:
    """The wheels inside a .zip upload (any folder depth); empty when there are none."""

    if not filename.endswith(".zip"):
        return []
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ExtensionValueError("The .zip file is damaged.") from None
    found = []
    for info in archive.infolist():
        name = info.filename.replace("\\", "/").split("/")[-1]
        if not info.is_dir() and name.lower().endswith(".whl") and not name.startswith("."):
            found.append((name, archive.read(info)))
    return found


def select_wheels(files: List[Tuple[str, bytes]], target: Path) -> List[str]:
    """
    Keep, per library, the wheel that best fits this Python and platform;
    returns the wheels that fit nothing here. Raises when a library has no
    fitting wheel at all.
    """

    from packaging.tags import sys_tags

    priority = {tag: index for index, tag in enumerate(sys_tags())}
    best: Dict[str, Tuple[int, str, bytes]] = {}
    unfit: List[str] = []
    seen: Dict[str, List[str]] = {}
    for name, data in files:
        try:
            project, version, _, tags = parse_wheel_filename(name)
        except Exception:
            raise ExtensionValueError(f"{name} is not a valid wheel file name.") from None
        canonical = canonicalize_name(str(project))
        seen.setdefault(canonical, []).append(name)
        rank = min((priority[tag] for tag in tags if tag in priority), default=None)
        if rank is None:
            unfit.append(name)
            continue
        current = best.get(canonical)
        if current is None or rank < current[0]:
            best[canonical] = (rank, name, data)
    stranded = [names for canonical, names in seen.items() if canonical not in best]
    if stranded:
        python = f"{sys.version_info[0]}.{sys.version_info[1]}"
        raise ExtensionValueError(
            "These wheels do not fit this server (Python "
            f"{python}, {_platform_name()}): {', '.join(n for names in stranded for n in names)}. "
            f"Download them for it, e.g. pip download <library> --python-version {python} "
            f"--platform {_pip_platform()} --only-binary=:all: -d wheels"
        )
    target.mkdir(parents=True, exist_ok=True)
    for _, name, data in best.values():
        (target / name).write_bytes(data)
    return unfit


def _platform_name() -> str:
    import platform

    return f"{platform.system()} {platform.machine()}"


def _pip_platform() -> str:
    from packaging.tags import sys_tags

    for tag in sys_tags():
        if tag.platform != "any":
            return tag.platform
    return "any"


def _wheel_metadata(wheel: Path) -> Tuple[str, str, List[str]]:
    """(name, version, Requires-Dist lines) from a wheel's METADATA."""

    with zipfile.ZipFile(wheel) as archive:
        metadata = next(
            (
                n
                for n in archive.namelist()
                if n.count("/") == 1 and n.endswith(".dist-info/METADATA")
            ),
            None,
        )
        if metadata is None:
            raise ExtensionValueError(f"{wheel.name} has no METADATA.")
        message = Parser().parsestr(archive.read(metadata).decode("utf-8", "replace"))
    return (
        message.get("Name") or "",
        message.get("Version") or "",
        message.get_all("Requires-Dist") or [],
    )


def missing_requirements(wheels: Path, host: Dict[str, str]) -> List[str]:
    """Dependencies of the wheels that neither the wheels nor Entropy provide."""

    from packaging.requirements import InvalidRequirement, Requirement

    present: Dict[str, str] = {}
    requirements: List[Tuple[str, str]] = []
    for wheel in wheels.glob("*.whl"):
        name, version, requires = _wheel_metadata(wheel)
        present[canonicalize_name(name)] = version
        requirements += [(name, line) for line in requires]
    missing = []
    for owner, line in requirements:
        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            continue
        # Optional extras ("; extra == 'gssapi'") and other platforms' markers.
        if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
            continue
        canonical = canonicalize_name(requirement.name)
        for source in (present, host):
            version = source.get(canonical)
            if version is not None and (
                not str(requirement.specifier)
                or requirement.specifier.contains(version, prereleases=True)
            ):
                break
        else:
            have = present.get(canonical) or host.get(canonical)
            missing.append(
                f"{requirement.name}{requirement.specifier or ''} (for {owner})"
                + (f", the zip has {have}" if have else "")
            )
    return sorted(set(missing))


def main_project(wheels: Path, name: Optional[str]) -> str:
    """The library a bundle is for: the given name, else the one nothing else depends on."""

    from packaging.requirements import InvalidRequirement, Requirement

    projects: Dict[str, str] = {}
    needed: set = set()
    for wheel in wheels.glob("*.whl"):
        project, _, requires = _wheel_metadata(wheel)
        projects[canonicalize_name(project)] = project
        for line in requires:
            try:
                needed.add(canonicalize_name(Requirement(line).name))
            except InvalidRequirement:
                continue
    if name:
        if canonicalize_name(name) not in projects:
            raise ExtensionValueError(
                f"The zip has no wheel for {name}; it has {', '.join(sorted(projects.values()))}."
            )
        return projects[canonicalize_name(name)]
    tops = [project for canonical, project in projects.items() if canonical not in needed]
    if len(tops) != 1:
        raise ExtensionValueError(
            "Say which library to install (Library field): the zip holds "
            f"{', '.join(sorted(projects.values()))}."
        )
    return tops[0]


def is_plain(filename: str, data: bytes) -> bool:
    """A .py module, or a .zip of a package folder without setup.py / pyproject.toml."""

    if filename.endswith(".py"):
        return True
    if not filename.endswith(".zip"):
        return False
    try:
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    except zipfile.BadZipFile:
        raise ExtensionValueError("The .zip file is damaged.") from None
    marks = ("setup.py", "pyproject.toml", "setup.cfg")
    return not any(name.split("/")[-1] in marks and name.count("/") <= 1 for name in names)


def make_wheel(
    filename: str, data: bytes, name: str, version: str, summary: str, target: Path
) -> Path:
    """
    A pure-Python wheel from a single module or a zipped package folder, so
    it installs, versions and travels like any other library.
    """

    name = check_name(name)
    version = check_version(version)
    files: Dict[str, bytes] = {}
    if filename.endswith(".py"):
        module = Path(filename).name
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*\.py$", module):
            raise ExtensionValueError(f"'{module}' is not a valid Python module name.")
        files[module] = data
    else:
        archive = zipfile.ZipFile(io.BytesIO(data))
        for info in archive.infolist():
            if info.is_dir():
                continue
            path = info.filename.replace("\\", "/")
            parts = [part for part in path.split("/") if part]
            if not parts or ".." in parts or path.startswith("/"):
                raise ExtensionValueError(f"The archive has an unsafe entry: {info.filename}")
            if "__pycache__" in parts or path.endswith((".pyc", ".pyo")):
                continue
            files["/".join(parts)] = archive.read(info)
        if not any(path.endswith(".py") for path in files):
            raise ExtensionValueError(
                "The archive has no Python files or wheels. Upload a zipped package folder, or a "
                ".zip of wheel files (.whl) such as pip download makes."
            )

    distribution = re.sub(r"[-.]+", "_", name)
    dist_info = f"{distribution}-{version}.dist-info"
    files[f"{dist_info}/METADATA"] = (
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nSummary: {summary or ''}\n"
    ).encode()
    files[f"{dist_info}/WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: entropy\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    record_rows = []
    for path, content in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        record_rows.append(f"{path},sha256={digest},{len(content)}")
    record_rows.append(f"{dist_info}/RECORD,,")
    files[f"{dist_info}/RECORD"] = ("\n".join(record_rows) + "\n").encode()

    target.mkdir(parents=True, exist_ok=True)
    wheel = target / f"{distribution}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return wheel


# ----------------------------------------------------------------------
# Moving versions between server and nodes
# ----------------------------------------------------------------------


def pack_wheels(wheels: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for wheel in sorted(wheels.glob("*.whl")):
            archive.add(wheel, arcname=wheel.name)
    return buffer.getvalue()


def unpack_wheels(data: bytes, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or "/" in member.name or not member.name.endswith(".whl"):
                raise ExtensionInstallationError("The extension bundle has an unexpected entry.")
            source = archive.extractfile(member)
            assert source is not None
            (target / member.name).write_bytes(source.read())


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def names(entries: Iterable[Dict[str, str]]) -> List[str]:
    return [f"{entry['name']}=={entry['version']}" for entry in entries]
