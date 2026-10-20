"""
Archives shipped to remote nodes: the Entropy runtime, plugin bundles
and a self-contained CPython for servers without a suitable Python.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import tarfile
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

# The vendored wheels are built for CPython 3.9, so nodes run 3.9 too.
PYTHON_VERSION = "3.9"

# python-build-standalone "install_only" builds (relocatable CPython).
CPYTHON_RELEASE = "20241016"
CPYTHON_FULL_VERSION = "3.9.20"
CPYTHON_BASE_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/" + CPYTHON_RELEASE
)
CPYTHON_TRIPLES = {
    "x86_64": "x86_64-unknown-linux-gnu",
    "amd64": "x86_64-unknown-linux-gnu",
    "aarch64": "aarch64-unknown-linux-gnu",
    "arm64": "aarch64-unknown-linux-gnu",
}

# Runtime contents relative to the project root.
RUNTIME_ITEMS = ("core", "lib", "entropy.py", "pyproject.toml", "resources")
EXCLUDED_PARTS = {"__pycache__", "node_modules", ".git", "frontend", "tests"}
EXCLUDED_PREFIXES = (
    # Wheels for other platforms are never needed on a Linux node.
    "resources/wheels/mac",
    "resources/wheels/windows",
    # Web UI wallpapers; nodes have no web UI.
    "lib/assets/",
)

# Not needed on nodes: the web server stays on the main node.
AGENT_EXCLUDED_REQUIREMENTS = ("fastapi", "uvicorn")


class PackagingError(Exception):
    """An archive could not be produced; the message is safe to show."""


def _include(relative: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if relative.suffix in (".pyc", ".pyo"):
        return False
    text = relative.as_posix()
    return not any(text.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def _files(root: Path, items: Iterable[str]) -> list:
    files = []
    for item in items:
        path = root / item
        if path.is_file():
            files.append(Path(item))
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                relative = child.relative_to(root)
                if child.is_file() and not child.is_symlink() and _include(relative):
                    files.append(relative)
    return sorted(files)


def _deterministic_tar(root: Path, files: Iterable[Path], prefix: str = "") -> bytes:
    """A gzip tar whose bytes depend only on file paths and contents."""

    buffer = io.BytesIO()
    # mtime=0 in the gzip header keeps the hash stable.
    with (
        gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for relative in files:
            path = root / relative
            info = tarfile.TarInfo(name=f"{prefix}{relative.as_posix()}")
            data = path.read_bytes()
            info.size = len(data)
            info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def runtime_bundle(project_root: Path, cache: Path) -> Tuple[Path, str]:
    """
    The Entropy runtime for nodes (code, resources and Linux wheels),
    cached by content hash. Returns (archive path, sha256).
    """

    files = _files(project_root, RUNTIME_ITEMS)
    fingerprint = hashlib.sha256()
    for relative in files:
        stat = (project_root / relative).stat()
        fingerprint.update(f"{relative}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    key = fingerprint.hexdigest()[:16]

    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"entropy-runtime-{key}.tar.gz"
    digest_file = archive.with_suffix(".sha256")

    if archive.exists() and digest_file.exists():
        return archive, digest_file.read_text().strip()

    data = _deterministic_tar(project_root, files)
    digest = hashlib.sha256(data).hexdigest()
    temporary = archive.with_suffix(".part")
    temporary.write_bytes(data)
    temporary.replace(archive)
    digest_file.write_text(digest)

    # Keep only the current runtime archive.
    for old in cache.glob("entropy-runtime-*.tar.gz"):
        if old != archive:
            old.unlink(missing_ok=True)
            old.with_suffix(".sha256").unlink(missing_ok=True)

    return archive, digest


def agent_requirements(project_root: Path) -> str:
    """The vendored requirements without the web server packages."""

    path = project_root / "resources" / "wheels" / "requirements.txt"
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.strip().split("=")[0].split(">")[0].split("<")[0].strip().lower()
        if (
            line.strip()
            and not line.strip().startswith("#")
            and name not in AGENT_EXCLUDED_REQUIREMENTS
        ):
            lines.append(line.strip())
    return "\n".join(lines) + "\n"


def plugin_bundle(path: Path) -> Tuple[bytes, str]:
    """A plugin directory as a deterministic archive, with its sha256."""

    files = [
        child.relative_to(path)
        for child in sorted(path.rglob("*"))
        if child.is_file() and not child.is_symlink() and _include(child.relative_to(path))
    ]
    data = _deterministic_tar(path, files)
    return data, hashlib.sha256(data).hexdigest()


def plugin_digest(path: Path, cache: Dict[str, Tuple[float, str]]) -> str:
    """sha256 of a plugin bundle, memoised on the directory's newest mtime."""

    newest = max(
        (child.stat().st_mtime for child in path.rglob("*") if child.is_file()),
        default=0.0,
    )
    key = str(path)
    if key in cache and cache[key][0] == newest:
        return cache[key][1]
    _, digest = plugin_bundle(path)
    cache[key] = (newest, digest)
    return digest


def cpython_archive(cache: Path, machine: str, *, download: bool = True) -> Path:
    """
    A relocatable CPython 3.9 for `machine` (uname -m). Uses a copy an
    administrator placed in the cache, else downloads and verifies one.
    """

    triple = CPYTHON_TRIPLES.get(machine.lower())
    if triple is None:
        raise PackagingError(
            f"No bundled Python is available for '{machine}'. Install Python {PYTHON_VERSION} "
            "with pip on the server and choose 'Use the server's Python'."
        )

    name = f"cpython-{CPYTHON_FULL_VERSION}+{CPYTHON_RELEASE}-{triple}-install_only.tar.gz"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / name
    if archive.exists():
        return archive

    if not download:
        raise PackagingError(
            f"Bundled Python is not available offline. Place {name} in {cache} "
            "on the Entropy server."
        )

    url = f"{CPYTHON_BASE_URL}/{name}"
    try:
        with urllib.request.urlopen(f"{url}.sha256", timeout=30) as response:
            expected = response.read().decode().split()[0].strip().lower()
        digest = hashlib.sha256()
        temporary = archive.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as handle:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                digest.update(chunk)
                handle.write(chunk)
    except OSError as exc:
        raise PackagingError(
            f"Could not download Python {CPYTHON_FULL_VERSION} ({exc}). Place {name} in {cache} "
            "on the Entropy server, or install Python 3.9 with pip on the node."
        ) from exc

    if digest.hexdigest() != expected:
        temporary.unlink()
        raise PackagingError("The downloaded Python archive failed its checksum; it was discarded.")

    temporary.replace(archive)
    return archive


def read_digest(path: Path) -> Optional[str]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
