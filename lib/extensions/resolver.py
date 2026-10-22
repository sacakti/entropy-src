"""
Which library version a plugin gets.

A plugin's `dependencies` in plugin.json name libraries and versions:

    {"name": "paramiko", "version": "3.0"}         exactly 3.0 (also 3.0.0)
    {"name": "requests", "version": ">=2.28,<3"}   any version in range
    {"name": "lxml"}                               any version

A requirement is met by the library Entropy itself runs with, when its
version fits, else by the newest fitting extension version. At run time
the chosen extension version is put first on the plugin's import path.
One process can use only one version of a library: two plugins of one
run that need different versions of the same library are refused.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from lib.extensions.exceptions import ExtensionValueError

# Libraries put on the import path in this process: canonical -> version.
_ACTIVE: Dict[str, str] = {}


class ExtensionConflictError(RuntimeError):
    """Two plugins in one process need different versions of a library."""


def specifier(version: Optional[str]) -> SpecifierSet:
    text = (version or "").strip()
    if text in ("", "*"):
        return SpecifierSet("")
    if text[0].isdigit():
        text = f"=={text}"
    try:
        return SpecifierSet(text)
    except InvalidSpecifier:
        raise ExtensionValueError(f"'{version}' is not a valid version requirement.") from None


def requirement_text(name: str, version: Optional[str]) -> str:
    spec = str(specifier(version))
    return f"{name}{spec}" if spec else name


def fits(version: str, spec: SpecifierSet) -> bool:
    try:
        return Version(version) in spec if str(spec) else True
    except InvalidVersion:
        return False


def resolve(
    requirements: Iterable[Any],
    installed: List[Dict[str, Any]],
    host: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    For each requirement (with .name and .version, or a dict): where it is
    met — {"name", "requirement", "status": "entropy" | "extension" |
    "missing", "version", "available": [installed extension versions]}.
    """

    by_name: Dict[str, List[str]] = {}
    for entry in installed:
        by_name.setdefault(entry["canonical"], []).append(entry["version"])
    result = []
    for requirement in requirements:
        name = requirement["name"] if isinstance(requirement, dict) else requirement.name
        version = (
            requirement.get("version") if isinstance(requirement, dict) else requirement.version
        )
        canonical = canonicalize_name(name)
        spec = specifier(version)
        available = sorted(by_name.get(canonical, []), key=Version, reverse=True)
        entry = {
            "name": name,
            "requirement": requirement_text(name, version),
            "spec": str(spec),
            "status": "missing",
            "version": None,
            "available": available,
            "entropy_version": host.get(canonical),
        }
        if canonical in host and fits(host[canonical], spec):
            entry.update(status="entropy", version=host[canonical])
        else:
            chosen = next((v for v in available if fits(v, spec)), None)
            if chosen:
                entry.update(status="extension", version=chosen)
        result.append(entry)
    return result


def activate(resolved: List[Dict[str, Any]], libraries: Path) -> List[str]:
    """Put the chosen extension versions on this process's import path."""

    added = []
    for entry in resolved:
        if entry["status"] != "extension":
            continue
        canonical = canonicalize_name(entry["name"])
        active = _ACTIVE.get(canonical)
        if active == entry["version"]:
            continue
        if active is not None:
            raise ExtensionConflictError(
                f"{entry['name']} {active} is already in use in this run; a plugin also needs "
                f"{entry['requirement']}. Run these plugins in separate workflows, or align their "
                "versions."
            )
        site = libraries / canonical / entry["version"] / "site"
        if not site.is_dir():
            raise ExtensionValueError(
                f"Extension {entry['name']} {entry['version']} is registered but its files are "
                "missing; reinstall it under Extensions."
            )
        sys.path.insert(0, str(site))
        _ACTIVE[canonical] = entry["version"]
        added.append(f"{entry['name']}=={entry['version']}")
    if added:
        importlib.invalidate_caches()
    return added
