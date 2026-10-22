"""
Upgrade an installation from a release package (entropy-<v>-<platform>.tar.gz).

Used by `ent upgrade --source` and Administration → System. Steps:

1. Inspect the package: format, platform, version, safe contents.
2. Extract it next to the application and install its Python packages
   into a fresh site-packages (same mode as at install time).
3. Swap application, site-packages and (when it changed) the bundled
   Python, keeping the previous ones.
4. Run the new code's finalize step: back up the database, migrate,
   reconcile permissions.
5. On any failure, put everything back, including the database.

The previous version stays on disk, so `rollback()` can return to it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import threading
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional

from . import install

PACKAGE_FORMAT = 2
MAX_PACKAGE_BYTES = 1 << 30

# One upgrade at a time per process; the lock file covers other processes.
_LOCK = threading.Lock()


class UpgradeError(Exception):
    """The upgrade could not be done; the message is safe to show."""


def _version_key(version: str) -> tuple:
    try:
        from packaging.version import Version

        return (0, Version(version))
    except Exception:  # noqa: BLE001 - unparsable versions compare as text
        return (1, version)


def _safe_members(archive: tarfile.TarFile) -> List[tarfile.TarInfo]:
    """Every member, refusing paths or links that would land outside the package."""

    members = archive.getmembers()
    for member in members:
        name = member.name
        parts = PurePosixPath(name).parts
        if name.startswith(("/", "\\")) or ".." in parts:
            raise UpgradeError(f"The package contains an unsafe path: {name}")
        if member.isdev():
            raise UpgradeError(f"The package contains a device file: {name}")
        if member.issym() or member.islnk():
            target = PurePosixPath(member.linkname)
            # Symbolic links resolve from the link's directory, hard links from the root.
            base = list(parts[:-1]) if member.issym() else []
            if target.is_absolute():
                raise UpgradeError(f"The package contains an unsafe link: {name}")
            depth = len(base)
            for part in target.parts:
                depth += -1 if part == ".." else (0 if part == "." else 1)
                if depth < 1:
                    raise UpgradeError(f"The package contains an unsafe link: {name}")
    return members


def read_manifest(package: Path) -> Dict[str, Any]:
    """The manifest of a release package, without extracting it."""

    if not package.is_file():
        raise UpgradeError(f"Package not found: {package}")
    if package.stat().st_size > MAX_PACKAGE_BYTES:
        raise UpgradeError("The package is larger than 1 GB.")

    try:
        with tarfile.open(package, "r:gz") as archive:
            for member in archive:
                parts = member.name.split("/")
                if len(parts) == 2 and parts[1] == "manifest.json" and member.isfile():
                    handle = archive.extractfile(member)
                    manifest = json.loads(handle.read().decode("utf-8")) if handle else {}
                    manifest["_root"] = parts[0]
                    return manifest
    except (tarfile.TarError, OSError, ValueError) as exc:
        raise UpgradeError(f"Not a valid Entropy release package: {exc}") from exc

    raise UpgradeError("Not an Entropy release package: manifest.json is missing.")


class ReleaseUpgrader:
    """Applies release packages to this installation."""

    def __init__(self, progress: Optional[Callable[[str], None]] = None) -> None:
        self.record = install.load()
        self.home = install.entropy_home()
        self.application = Path(self.record["application"])
        self.root = self.application.parent
        self.packages = self.home / "site-packages"
        self._progress = progress or (lambda message: None)

    def say(self, message: str) -> None:
        self._progress(message)

    # ------------------------------------------------------------------
    # Inspect
    # ------------------------------------------------------------------

    def inspect(self, package: Path) -> Dict[str, Any]:
        from core.version import VERSION

        manifest = read_manifest(package)
        problems: List[str] = []

        if manifest.get("format") != PACKAGE_FORMAT or manifest.get("name") != "entropy":
            problems.append("This is not an Entropy release package (unknown format).")

        if not install.record_path().exists():
            problems.append(
                "This Entropy runs from a source checkout, not an installation; "
                "release packages cannot upgrade it."
            )

        platform = self.record.get("platform")
        if platform and manifest.get("platform") != platform:
            problems.append(
                f"The package is for {manifest.get('platform')}, this installation is {platform}."
            )

        version = str(manifest.get("version", ""))
        newer = _version_key(version) > _version_key(VERSION)
        same = version == VERSION

        return {
            "version": version,
            "current": VERSION,
            "platform": manifest.get("platform"),
            "python": manifest.get("python"),
            "upgrade_only": bool(manifest.get("upgrade_only", False)),
            "built_at": manifest.get("built_at"),
            "newer": newer,
            "same": same,
            "problems": problems,
            "size": package.stat().st_size,
        }

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(
        self, package: Path, *, allow_downgrade: bool = False, user: str = ""
    ) -> Dict[str, Any]:
        if not _LOCK.acquire(blocking=False):
            raise UpgradeError("An upgrade is already running.")
        lock_file = self.home / "run" / "upgrade.lock"
        try:
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                raise UpgradeError(
                    f"An upgrade is already running (remove {lock_file} if it is stale)."
                ) from exc
            os.close(descriptor)
            try:
                return self._apply(package, allow_downgrade, user)
            finally:
                lock_file.unlink(missing_ok=True)
        finally:
            _LOCK.release()

    def _apply(self, package: Path, allow_downgrade: bool, user: str) -> Dict[str, Any]:
        info = self.inspect(package)
        if info["problems"]:
            raise UpgradeError(" ".join(info["problems"]))
        if not info["newer"] and not allow_downgrade:
            raise UpgradeError(
                f"Version {info['version']} is not newer than the installed {info['current']}."
                " Allow a downgrade/reinstall to apply it anyway."
            )

        staging = self.root / "upgrade-staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        components = (
            (self.application,)
            if info["upgrade_only"]
            else (self.application, self.packages, self.root / "python")
        )
        for component in components:
            stale = self._previous(component)
            if stale.exists():
                shutil.rmtree(stale)

        swapped: List[tuple] = []
        backup: Optional[Path] = None
        database: Optional[Path] = None
        try:
            self.say(f"Extracting Entropy {info['version']}…")
            with tarfile.open(package, "r:gz") as archive:
                members = _safe_members(archive)
                options = {"filter": "tar"} if hasattr(tarfile, "tar_filter") else {}
                archive.extractall(staging, members=members, **options)
            extracted = staging / read_manifest(package)["_root"]
            packaged_application = extracted / "application"
            if not (packaged_application / "entropy.py").is_file():
                raise UpgradeError("The package does not contain the Entropy application.")

            if info["upgrade_only"]:
                # Upgrade packages carry application files only. Start with
                # the installed tree so unshipped runtime assets (notably
                # wheels and frontend files) remain available, then overlay
                # the package's updated code and resources.
                new_application = staging / "application.new"
                shutil.copytree(self.application, new_application)
                shutil.copytree(packaged_application, new_application, dirs_exist_ok=True)
            else:
                new_application = packaged_application

            python = Path(self.record["python"])
            bundled_root = self.root / "python"
            staged_python_root = None
            if (
                not info["upgrade_only"]
                and bundled_root in python.parents
                and (extracted / "python").is_dir()
                and self._bundled_version(python) != info["python"]
            ):
                staged_python_root = extracted / "python"
                python = staged_python_root / python.relative_to(bundled_root)
                self.say(f"The package brings Python {info['python']}.")

            new_packages = self.home / "site-packages.new"
            if not info["upgrade_only"]:
                self.say("Installing Python packages…")
                self._install_packages(python, new_application, new_packages)

            self.say("Switching to the new version…")
            swapped.append(self._swap(self.application, new_application))
            if not info["upgrade_only"]:
                swapped.append(self._swap(self.packages, new_packages))
            if staged_python_root is not None:
                swapped.append(self._swap(bundled_root, staged_python_root))

            self.say("Migrating the database…")
            outcome = self._finalize(info["version"])
            database = Path(outcome["database"])
            backup = Path(outcome["backup"]) if outcome.get("backup") else None
        except Exception as exc:
            self.say("Upgrade failed; restoring the previous version…")
            for current, previous in reversed(swapped):
                self._unswap(current, previous)
            if database is not None and backup is not None:
                from .finalize import restore

                restore(database, backup)
            shutil.rmtree(staging, ignore_errors=True)
            if not info["upgrade_only"]:
                shutil.rmtree(self.home / "site-packages.new", ignore_errors=True)
            if isinstance(exc, UpgradeError):
                raise
            raise UpgradeError(f"{exc.__class__.__name__}: {exc}") from exc

        shutil.rmtree(staging, ignore_errors=True)

        entry = {
            "from": info["current"],
            "to": info["version"],
            "upgrade_only": info["upgrade_only"],
            "at": datetime.now(timezone.utc).isoformat(),
            "by": user,
            "database": str(database) if database else None,
            "database_backup": str(backup) if backup else None,
        }
        record = install.load()
        record["version"] = info["version"]
        record.setdefault("upgrades", []).append(entry)
        record["upgrades"] = record["upgrades"][-20:]
        install.save(record)
        self.say(f"Entropy {info['version']} is installed.")
        return entry

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def can_rollback(self) -> bool:
        upgrades = self.record.get("upgrades") or []
        return (
            bool(upgrades)
            and not upgrades[-1].get("rollback")
            and self._previous(self.application).exists()
        )

    def rollback(self, user: str = "") -> Dict[str, Any]:
        """Return to the version before the last upgrade, database included."""

        if not self.can_rollback():
            raise UpgradeError("There is no previous version to return to.")

        last = self.record["upgrades"][-1]
        components = (
            (self.application,)
            if last.get("upgrade_only", False)
            else (self.application, self.packages, self.root / "python")
        )
        for current in components:
            previous = self._previous(current)
            if previous.exists():
                self._unswap(current, previous)

        if last.get("database") and last.get("database_backup"):
            from .finalize import restore

            restore(Path(last["database"]), Path(last["database_backup"]))

        entry = {
            "from": last["to"],
            "to": last["from"],
            "at": datetime.now(timezone.utc).isoformat(),
            "by": user,
            "rollback": True,
            "upgrade_only": last.get("upgrade_only", False),
            "database": None,
            "database_backup": None,
        }
        record = install.load()
        record["version"] = last["from"]
        record.setdefault("upgrades", []).append(entry)
        record["upgrades"] = record["upgrades"][-20:]
        install.save(record)
        return entry

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _previous(path: Path) -> Path:
        return path.with_name(path.name + ".previous")

    def _swap(self, current: Path, replacement: Path) -> tuple:
        """Move `current` aside (as .previous) and put `replacement` in place."""

        previous = self._previous(current)
        if previous.exists():
            shutil.rmtree(previous)
        if current.exists():
            current.rename(previous)
        shutil.move(str(replacement), str(current))
        return (current, previous)

    @staticmethod
    def _unswap(current: Path, previous: Path) -> None:
        if previous.exists():
            if current.exists():
                shutil.rmtree(current)
            previous.rename(current)

    @staticmethod
    def _bundled_version(python: Path) -> Optional[str]:
        try:
            result = subprocess.run(
                [str(python), "-c", "import platform; print(platform.python_version())"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return result.stdout.strip() or None
        except OSError:
            return None

    def _install_packages(self, python: Path, application: Path, target: Path) -> None:
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)

        requirements = application / "resources" / "wheels" / "requirements.txt"
        mode = self.record.get("deps", "bundled")

        if mode == "manual":
            # Packages live in the runtime Python; only verify them.
            self._verify_packages(python, application, target)
            return

        command = [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "--target",
            str(target),
            "-r",
            str(requirements),
        ]
        if mode == "index":
            if self.record.get("index_url"):
                command.extend(["--index-url", self.record["index_url"]])
        else:
            wheels = [
                path
                for path in (application / "resources" / "wheels").iterdir()
                if path.is_dir() and any(path.glob("*.whl"))
            ]
            if not wheels:
                raise UpgradeError("The package carries no Python wheels.")
            command.extend(["--no-index", "--find-links", str(wheels[0])])

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr.strip() or result.stdout.strip()).splitlines()
            raise UpgradeError(
                "Installing Python packages failed: " + (detail[-1] if detail else "pip error")
            )
        self._verify_packages(python, application, target)

    @staticmethod
    def _verify_packages(python: Path, application: Path, target: Path) -> None:
        probe = (
            "import importlib.util, sys\n"
            f"sys.path.insert(0, {str(target)!r})\n"
            "from lib.install.wheels import REQUIRED_MODULES\n"
            "missing = [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]\n"
            "print(','.join(missing))\n"
        )
        result = subprocess.run(
            [str(python), "-c", probe],
            cwd=str(application),
            capture_output=True,
            text=True,
            check=False,
        )
        missing = [name for name in result.stdout.strip().split(",") if name]
        if result.returncode != 0 or missing:
            raise UpgradeError(
                "Python packages missing for the new version: "
                f"{', '.join(missing) or result.stderr.strip()[-300:]}"
            )

    def _finalize(self, version: str) -> Dict[str, Any]:
        python = Path(install.load()["python"])
        environment = dict(os.environ)
        environment["ENTROPY_HOME"] = str(self.home)
        environment.pop("PYTHONPATH", None)
        result = subprocess.run(
            [str(python), "-m", "lib.system.finalize", version],
            cwd=str(self.application),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
        try:
            outcome = json.loads(lines[-1]) if lines else {}
        except ValueError:
            outcome = {}
        if result.returncode != 0 or not outcome.get("ok"):
            detail = (
                outcome.get("error")
                or (result.stderr.strip().splitlines() or ["unknown error"])[-1]
            )
            raise UpgradeError(f"The new version could not migrate the database: {detail}")
        return outcome
