"""
Plugin workspace operations for the web editor.

Installed plugins are never edited in place. Every change is staged in a
temporary copy, checked, and then installed through the plugin manager so the
installer's manifest validation, migrations, and registry updates still apply.
If reinstalling fails, the previous installation is restored.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import threading
from pathlib import Path, PurePosixPath
from typing import Any

from core.constants import PLUGIN_DIRECTORIES, PLUGIN_FILES
from core.generators.validators.plugin import PluginValidator
from core.version import VERSION
from core.web.plugin_studio.analysis import Diagnostic, check_files, check_manifest
from lib.plugins.manifest import ManifestReader
from lib.plugins.validator import ManifestValidator

EDITABLE_SUFFIXES = (".py", ".json", ".md", ".txt")
MAX_FILE_BYTES = 512_000
MAX_FILES = 200
MAX_DESCRIPTION_LENGTH = 200
IGNORED_PARTS = {"__pycache__"}
PATH_SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


class PluginStudioError(Exception):
    """Base error carrying the HTTP status the route should answer with."""

    status_code = 422


class PluginConflictError(PluginStudioError):
    status_code = 409


class PluginValidationFailed(PluginStudioError):
    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        super().__init__("Plugin validation failed.")
        self.diagnostics = diagnostics


# ----------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------


def normalize_path(path: str) -> str:
    """Return a safe plugin-relative POSIX path or raise PluginStudioError."""

    candidate = PurePosixPath(path.strip().replace("\\", "/"))
    parts = candidate.parts

    if (
        not parts
        or candidate.is_absolute()
        or any(not PATH_SEGMENT.fullmatch(part) or part in IGNORED_PARTS for part in parts)
        or candidate.suffix not in EDITABLE_SUFFIXES
    ):
        raise PluginStudioError(
            f"'{path}' is not an editable plugin file. "
            f"Use a relative path ending in {', '.join(EDITABLE_SUFFIXES)}."
        )

    return candidate.as_posix()


def read_files(root: Path) -> dict[str, str]:
    """Read the editable text files of a plugin directory."""

    files: dict[str, str] = {}

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)

        if (
            not path.is_file()
            or path.is_symlink()
            or path.suffix not in EDITABLE_SUFFIXES
            or any(part.startswith(".") or part in IGNORED_PARTS for part in relative.parts)
            or path.stat().st_size > MAX_FILE_BYTES
        ):
            continue

        try:
            files[relative.as_posix()] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if len(files) >= MAX_FILES:
            break

    return files


def revision(files: dict[str, str]) -> str:
    """Fingerprint a file map so concurrent edits can be detected."""

    digest = hashlib.sha256()

    for path in sorted(files):
        digest.update(path.encode("utf-8") + b"\0")
        digest.update(files[path].encode("utf-8") + b"\0")

    return digest.hexdigest()


def _stage(source: Path, destination: Path, changes: dict[str, str]) -> Path:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(*IGNORED_PARTS),
    )

    for path, content in changes.items():
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    return destination


def _normalize_changes(changes: dict[str, str]) -> dict[str, str]:
    if len(changes) > MAX_FILES:
        raise PluginStudioError("Too many files in one save.")

    normalized: dict[str, str] = {}

    for path, content in changes.items():
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise PluginStudioError(f"'{path}' is too large.")

        normalized[normalize_path(path)] = content

    return normalized


# ----------------------------------------------------------------------
# Studio
# ----------------------------------------------------------------------


class PluginStudio:
    """Create, edit, and delete installed plugins on behalf of the web UI."""

    # Mutations reinstall plugins; serialize them across request threads.
    _lock = threading.Lock()

    def __init__(self, context: Any) -> None:
        self._context = context
        self._manager = context.plugin_manager
        self._reader = ManifestReader(context)
        self._validator = ManifestValidator(entropy_version=VERSION)

    # -- identity -------------------------------------------------------

    def check_name(self, namespace: str, name: str) -> None:
        """Raise when a namespace/name pair is invalid or already taken."""

        try:
            PluginValidator.validate_namespace(namespace)
            PluginValidator.validate_name(name)
        except Exception as exc:
            raise PluginStudioError(str(exc)) from exc

        qualified_name = f"{namespace}.{name}"

        if self._manager.exists(qualified_name):
            raise PluginConflictError(f"Plugin '{qualified_name}' already exists.")

        if (self._context.paths.plugins.directory / namespace / name).exists():
            raise PluginConflictError(
                f"A plugin directory for '{qualified_name}' already exists on disk."
            )

    # -- create ---------------------------------------------------------

    def create(self, namespace: str, name: str, description: str = "") -> Any:
        """Render the plugin template and install the result."""

        description = description.strip()

        if len(description) > MAX_DESCRIPTION_LENGTH or re.search(r'["\\\r\n]', description):
            raise PluginStudioError(
                f"Description must be a single line of at most {MAX_DESCRIPTION_LENGTH} "
                "characters without quotes or backslashes."
            )

        with self._lock:
            self.check_name(namespace, name)

            render_context = {
                "namespace": namespace,
                "name": name,
                "qualified_name": f"{namespace}.{name}",
                "class_name": "".join(part.capitalize() for part in name.split("_")) + "Plugin",
                "version": "1.0.0",
                "description": description,
                "author": "",
                "license": "",
            }

            with tempfile.TemporaryDirectory(prefix="entropy-web-plugin-") as directory:
                staged = Path(directory) / name

                for template, filename in PLUGIN_FILES:
                    self._context.template.render(template, staged / filename, render_context)

                for child in PLUGIN_DIRECTORIES:
                    (staged / child).mkdir(parents=True, exist_ok=True)

                return self._manager.install(staged)

    # -- read -----------------------------------------------------------

    def files(self, qualified_name: str) -> dict[str, Any]:
        plugin = self._manager.get(qualified_name)
        files = read_files(plugin.path)

        return {
            "plugin": plugin,
            "files": files,
            "revision": revision(files),
        }

    # -- validate -------------------------------------------------------

    def validate(self, qualified_name: str, changes: dict[str, str]) -> list[Diagnostic]:
        plugin = self._manager.get(qualified_name)
        changes = _normalize_changes(changes)

        with tempfile.TemporaryDirectory(prefix="entropy-web-plugin-") as directory:
            return self._diagnostics(plugin, changes, Path(directory))

    def _diagnostics(
        self, plugin: Any, changes: dict[str, str], directory: Path
    ) -> list[Diagnostic]:
        staged = _stage(plugin.path, directory / plugin.name, changes)
        files = {**read_files(plugin.path), **changes}

        return check_files(files) + check_manifest(
            staged,
            plugin.namespace,
            plugin.name,
            self._reader,
            self._validator,
        )

    # -- save -----------------------------------------------------------

    def save(
        self,
        qualified_name: str,
        changes: dict[str, str],
        base_revision: str,
    ) -> dict[str, Any]:
        changes = _normalize_changes(changes)

        with self._lock:
            plugin = self._manager.get(qualified_name)

            if revision(read_files(plugin.path)) != base_revision:
                raise PluginConflictError(
                    f"Plugin '{qualified_name}' changed since it was opened. "
                    "Reload it and reapply your edits."
                )

            with tempfile.TemporaryDirectory(prefix="entropy-web-plugin-") as directory:
                root = Path(directory)
                source = root / "source"
                source.mkdir()

                diagnostics = self._diagnostics(plugin, changes, source)

                if any(item.severity == "error" for item in diagnostics):
                    raise PluginValidationFailed(diagnostics)

                staged = source / plugin.name
                backup = shutil.copytree(plugin.path, root / "backup" / plugin.name)

                try:
                    self._manager.repair(qualified_name, staged)
                except Exception:
                    if not self._manager.exists(qualified_name):
                        self._manager.install(backup)
                        if not plugin.enabled:
                            self._manager.disable(qualified_name)
                    raise

            if not plugin.enabled:
                self._manager.disable(qualified_name)

        return self.files(qualified_name)

    # -- delete ---------------------------------------------------------

    def delete(self, qualified_name: str) -> None:
        with self._lock:
            self._manager.uninstall(qualified_name)
