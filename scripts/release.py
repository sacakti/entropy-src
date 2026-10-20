#!/usr/bin/env python3
"""
Build a self-contained Entropy release package:

    entropy-<version>-<platform>.tar.gz
        install.sh | install.cmd    installer entry point
        manifest.json               version, platform, Python, contents
        python/                     relocatable CPython 3.9
        application/                Entropy, the built web UI and the
                                    platform's Python wheels

Nothing else is needed on the target: no Python, venv, pip or npm.

Usage:
    python3 scripts/release.py --platform linux-x86_64
    python3 scripts/release.py --platform windows-x86_64 --version 1.2.0
    python3 scripts/release.py --all

Building needs network access (wheels and CPython are downloaded and
cached under build/cache) and Node.js unless --skip-frontend is given
with an existing frontend/dist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from lib.nodes.packaging import (  # noqa: E402
    CPYTHON_FULL_VERSION,
    PackagingError,
    cpython_archive_for,
)

PACKAGE_FORMAT = 2
TEMPLATES = PROJECT_ROOT / "scripts" / "release_templates"

# platform -> (wheel directory, CPython triple, pip platform tags, installer)
PLATFORMS = {
    "linux-x86_64": (
        "linux",
        "x86_64-unknown-linux-gnu",
        ("manylinux2014_x86_64", "manylinux_2_17_x86_64", "manylinux_2_28_x86_64"),
        "install.sh",
    ),
    "linux-aarch64": (
        "linux",
        "aarch64-unknown-linux-gnu",
        ("manylinux2014_aarch64", "manylinux_2_17_aarch64", "manylinux_2_28_aarch64"),
        "install.sh",
    ),
    "macos-arm64": (
        "mac",
        "aarch64-apple-darwin",
        ("macosx_11_0_arm64", "macosx_12_0_arm64", "macosx_14_0_arm64"),
        "install.sh",
    ),
    "macos-x86_64": (
        "mac",
        "x86_64-apple-darwin",
        ("macosx_10_9_x86_64", "macosx_10_12_x86_64", "macosx_11_0_x86_64"),
        "install.sh",
    ),
    "windows-x86_64": (
        "windows",
        "x86_64-pc-windows-msvc",
        ("win_amd64",),
        "install.cmd",
    ),
}

# Dependencies that environment markers would hide when resolving on a
# different operating system than the target.
PLATFORM_EXTRAS = {
    "windows": ("colorama", "tzdata"),
}

# The build host's CPython 3.9 resolves the wheel set, so markers such as
# python_version < "3.10" are evaluated for the runtime Python.
HOST_TRIPLES = {
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
}

APPLICATION_ITEMS = ("core", "lib", "resources", "entropy.py", "pyproject.toml")
EXCLUDED = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store"}


class ReleaseError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"==> {message}", flush=True)


def current_version() -> str:
    from core.version import VERSION

    return VERSION


# ----------------------------------------------------------------------
# Pieces
# ----------------------------------------------------------------------


def build_frontend(skip: bool) -> Path:
    frontend = PROJECT_ROOT / "frontend"
    dist = frontend / "dist"

    if not skip:
        npm = shutil.which("npm")
        if npm is None:
            raise ReleaseError("npm is needed to build the web UI (or pass --skip-frontend).")
        if not (frontend / "node_modules").is_dir():
            log("Installing web UI build dependencies (npm ci)")
            subprocess.run([npm, "ci"], cwd=frontend, check=True)
        log("Building the web UI")
        subprocess.run([npm, "run", "build"], cwd=frontend, check=True)

    if not (dist / "index.html").is_file():
        raise ReleaseError("frontend/dist/index.html is missing; build the web UI first.")
    return dist


def resolver_python(cache: Path) -> str:
    """A CPython 3.9 that runs on the build host, to resolve wheels with."""

    if sys.version_info[:2] == (3, 9):
        return sys.executable

    import platform as host

    triple = HOST_TRIPLES.get((host.system(), host.machine()))
    if triple is None:
        raise ReleaseError("Run the release build with Python 3.9 on this host.")

    root = cache / "host-python" / triple
    python = root / "python" / ("python.exe" if host.system() == "Windows" else "bin/python3")
    if not python.exists():
        log(f"Fetching CPython {CPYTHON_FULL_VERSION} for the build host")
        try:
            archive = cpython_archive_for(cache / "python", triple)
        except PackagingError as exc:
            raise ReleaseError(str(exc)) from exc
        root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as source:
            options = {"filter": "tar"} if hasattr(tarfile, "tar_filter") else {}
            source.extractall(root, **options)
    return str(python)


def download_wheels(platform: str, destination: Path, cache: Path, offline: Path | None) -> None:
    wheel_dir, _, tags, _ = PLATFORMS[platform]
    requirements = PROJECT_ROOT / "resources" / "wheels" / "requirements.txt"
    destination.mkdir(parents=True, exist_ok=True)

    if offline is not None:
        log(f"Using pre-downloaded wheels from {offline}")
        for wheel in offline.glob("*.whl"):
            shutil.copy2(wheel, destination / wheel.name)
        return

    target = cache / "wheels" / platform
    target.mkdir(parents=True, exist_ok=True)
    combined = cache / f"requirements-{platform}.txt"
    combined.write_text(
        requirements.read_text(encoding="utf-8").rstrip()
        + "\n"
        + "".join(f"{extra}\n" for extra in PLATFORM_EXTRAS.get(wheel_dir, ())),
        encoding="utf-8",
    )
    log(f"Downloading Python wheels for {platform} (CPython 3.9)")
    command = [
        resolver_python(cache),
        "-m",
        "pip",
        "download",
        "--disable-pip-version-check",
        "--quiet",
        "--only-binary=:all:",
        "--implementation",
        "cp",
        "--python-version",
        "3.9",
        "--dest",
        str(target),
        "-r",
        str(combined),
    ]
    for tag in tags:
        command.extend(["--platform", tag])
    try:
        subprocess.run(command, check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        vendored = PROJECT_ROOT / "resources" / "wheels" / wheel_dir
        raise ReleaseError(
            f"Downloading wheels failed ({exc}). Provide them with --wheels DIR "
            f"(e.g. the vendored {vendored})."
        ) from exc

    for wheel in target.glob("*.whl"):
        shutil.copy2(wheel, destination / wheel.name)


def extract_python(platform: str, destination: Path, cache: Path, archive: Path | None) -> str:
    _, triple, _, _ = PLATFORMS[platform]
    if archive is None:
        log(f"Fetching CPython {CPYTHON_FULL_VERSION} for {triple}")
        try:
            archive = cpython_archive_for(cache / "python", triple)
        except PackagingError as exc:
            raise ReleaseError(str(exc)) from exc

    with tarfile.open(archive) as source:
        for member in source.getmembers():
            if member.name.startswith(("/", "..")) or "/../" in member.name:
                raise ReleaseError(f"Unsafe path in {archive.name}: {member.name}")
        # Python 3.12+ can filter members; 'tar' keeps the runtime's symlinks.
        options = {"filter": "tar"} if hasattr(tarfile, "tar_filter") else {}
        source.extractall(destination.parent, **options)

    extracted = destination.parent / "python"
    if extracted != destination:
        extracted.rename(destination)
    return CPYTHON_FULL_VERSION


def copy_application(destination: Path, platform: str, version: str, dist: Path) -> None:
    wheel_dir = PLATFORMS[platform][0]

    def ignore(directory: str, names: list) -> set:
        skipped = {name for name in names if name in EXCLUDED or name.endswith((".pyc", ".pyo"))}
        if Path(directory) == PROJECT_ROOT / "resources" / "wheels":
            # Only this platform's wheels, refreshed below.
            skipped |= {name for name in names if name != "requirements.txt"}
        return skipped

    destination.mkdir(parents=True)
    for item in APPLICATION_ITEMS:
        source = PROJECT_ROOT / item
        if source.is_dir():
            shutil.copytree(source, destination / item, ignore=ignore)
        else:
            shutil.copy2(source, destination / item)

    (destination / "resources" / "wheels" / wheel_dir).mkdir(parents=True, exist_ok=True)
    shutil.copytree(dist, destination / "frontend" / "dist")

    # The release carries a fixed version.
    (destination / "core" / "version.py").write_text(
        '"""\nApplication version information.\n"""\n\n'
        'APP_NAME = "Entropy"\n\n'
        f'VERSION = "{version}"\n\n'
        'AUTHOR = "Aravinthan"\n\n'
        'COPYRIGHT = "© 2026 Entropy Deployment Framework"\n',
        encoding="utf-8",
    )


def write_installer(stage: Path, platform: str) -> None:
    name = PLATFORMS[platform][3]
    target = stage / name
    shutil.copy2(TEMPLATES / name, target)
    target.chmod(0o755)
    shutil.copy2(TEMPLATES / "README.txt", stage / "README.txt")


def archive(stage: Path, output: Path) -> str:
    log(f"Writing {output.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".part")

    def reset(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        return info

    with tarfile.open(temporary, "w:gz", compresslevel=9) as tar:
        tar.add(stage, arcname=stage.name, filter=reset)

    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    temporary.replace(output)
    output.with_name(output.name + ".sha256").write_text(f"{digest}  {output.name}\n")
    return digest


# ----------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------


def build(platform: str, version: str, args: argparse.Namespace, dist: Path) -> Path:
    if platform not in PLATFORMS:
        raise ReleaseError(f"Unknown platform '{platform}'. Choose from: {', '.join(PLATFORMS)}.")

    build_root = PROJECT_ROOT / "build"
    cache = build_root / "cache"
    stage = build_root / "release" / f"entropy-{version}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    log(f"Staging Entropy {version} for {platform}")
    copy_application(stage / "application", platform, version, dist)
    wheel_dir = PLATFORMS[platform][0]
    download_wheels(
        platform,
        stage / "application" / "resources" / "wheels" / wheel_dir,
        cache,
        args.wheels,
    )
    python_version = extract_python(platform, stage / "python", cache, args.python_archive)
    write_installer(stage, platform)

    wheels = sorted(
        p.name for p in (stage / "application" / "resources" / "wheels" / wheel_dir).glob("*.whl")
    )
    manifest = {
        "format": PACKAGE_FORMAT,
        "name": "entropy",
        "version": version,
        "platform": platform,
        "python": python_version,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "installer": PLATFORMS[platform][3],
        "wheels": wheels,
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    output = (args.output or build_root / "dist") / f"entropy-{version}-{platform}.tar.gz"
    digest = archive(stage, output)
    shutil.rmtree(stage)

    size = output.stat().st_size / (1 << 20)
    log(f"Built {output} ({size:.1f} MB, sha256 {digest[:16]}…)")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Entropy release packages.")
    parser.add_argument("--platform", action="append", choices=sorted(PLATFORMS))
    parser.add_argument("--all", action="store_true", help="Build every platform.")
    parser.add_argument("--version", help="Release version (default: core/version.py).")
    parser.add_argument("--output", type=Path, help="Output directory (default build/dist).")
    parser.add_argument(
        "--skip-frontend", action="store_true", help="Use the existing frontend/dist."
    )
    parser.add_argument(
        "--wheels", type=Path, help="Use pre-downloaded wheels from this directory."
    )
    parser.add_argument(
        "--python-archive", type=Path, help="Use this python-build-standalone archive."
    )
    args = parser.parse_args()

    platforms = sorted(PLATFORMS) if args.all else (args.platform or ["linux-x86_64"])
    if len(platforms) > 1 and (args.wheels or args.python_archive):
        parser.error("--wheels and --python-archive apply to a single --platform.")

    try:
        version = args.version or current_version()
        dist = build_frontend(args.skip_frontend)
        for platform in platforms:
            build(platform, version, args, dist)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"Release failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
