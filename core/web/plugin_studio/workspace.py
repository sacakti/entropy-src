"""
Plugin workspace operations for the web editor.

Installed plugins are never edited in place. Every change is staged in a
temporary copy, checked, and then installed through the plugin manager so the
installer's manifest validation, migrations, and registry updates still apply.
If reinstalling fails, the previous installation is restored.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, Callable, Optional, Sequence

from core.constants import PLUGIN_DIRECTORIES, PLUGIN_FILES
from core.generators.validators.plugin import PluginValidator
from core.version import VERSION
from core.web.plugin_studio.analysis import Diagnostic, check_files, check_manifest
from core.web.versioning import bump_version
from lib.plugins.manifest import ManifestReader
from lib.plugins.validator import ManifestValidator

EDITABLE_SUFFIXES = (".py", ".json", ".md", ".txt")
MAX_FILE_BYTES = 512_000
MAX_FILES = 200
MAX_DESCRIPTION_LENGTH = 200
IGNORED_PARTS = {"__pycache__"}
PATH_SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
MAX_IMPORT_BYTES = 20_000_000
MANIFEST_VERSION = re.compile(r'("version"\s*:\s*")([^"]*)(")')


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


def _stage(
    source: Path, destination: Path, changes: dict[str, str], removed: Sequence[str] = ()
) -> Path:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(*IGNORED_PARTS),
    )

    for path in removed:
        with contextlib.suppress(FileNotFoundError):
            (destination / path).unlink()

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


# Called with a plugin's files and version just before they are replaced.
Backup = Callable[[dict, str], None]


def _manifest_version(files: dict[str, str]) -> str:
    match = MANIFEST_VERSION.search(files.get("plugin.json", ""))
    return match.group(2) if match else ""


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

        if self._draft_path(namespace, name).exists():
            raise PluginConflictError(f"A draft named '{qualified_name}' already exists.")

    # -- drafts ---------------------------------------------------------

    @property
    def drafts_root(self) -> Path:
        return Path(self._context.bootstrap.home) / "plugin_drafts"

    def _draft_path(self, namespace: str, name: str) -> Path:
        return self.drafts_root / namespace / name

    def _draft(self, namespace: str, name: str) -> Any:
        path = self._draft_path(namespace, name)
        version = ""
        with contextlib.suppress(OSError, ValueError, AttributeError):
            version = str(json.loads((path / "plugin.json").read_text("utf-8")).get("version", ""))
        return SimpleNamespace(
            id=None,
            namespace=namespace,
            name=name,
            path=path,
            version=version,
            enabled=False,
            installed_at=None,
            draft=True,
        )

    def drafts(self) -> list[Any]:
        root = self.drafts_root
        if not root.is_dir():
            return []
        return [
            self._draft(path.parent.name, path.name)
            for path in sorted(root.glob("*/*"))
            if path.is_dir() and (path / "plugin.json").is_file()
        ]

    def _resolve(self, qualified_name: str) -> Any:
        """An installed plugin, else a draft of that name."""

        if self._manager.exists(qualified_name):
            return self._manager.get(qualified_name)

        namespace, _, name = qualified_name.partition(".")
        if (
            PATH_SEGMENT.fullmatch(namespace)
            and PATH_SEGMENT.fullmatch(name)
            and (self._draft_path(namespace, name) / "plugin.json").is_file()
        ):
            return self._draft(namespace, name)

        return self._manager.get(qualified_name)  # raises PluginNotFoundError

    def install(self, qualified_name: str) -> Any:
        """Install a draft after it passes validation, then drop the draft."""

        draft = self._resolve(qualified_name)
        if not getattr(draft, "draft", False):
            raise PluginConflictError(f"Plugin '{qualified_name}' is already installed.")

        with tempfile.TemporaryDirectory(prefix="entropy-web-plugin-") as directory:
            diagnostics = self._diagnostics(draft, {}, Path(directory))
        if any(item.severity == "error" for item in diagnostics):
            raise PluginValidationFailed(diagnostics)

        with self._lock:
            plugin = self._manager.install(draft.path)
            shutil.rmtree(draft.path, ignore_errors=True)
            with contextlib.suppress(OSError):
                draft.path.parent.rmdir()

        return plugin

    # -- export / import ------------------------------------------------

    def export(self, qualified_names: list[str]) -> bytes:
        """A zip with one folder per plugin (installed or draft)."""

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for qualified_name in qualified_names:
                plugin = self._resolve(qualified_name)
                for path in sorted(plugin.path.rglob("*")):
                    relative = path.relative_to(plugin.path)
                    if (
                        path.is_file()
                        and not path.is_symlink()
                        and not any(
                            part in IGNORED_PARTS or part.startswith(".") for part in relative.parts
                        )
                    ):
                        archive.write(path, f"{qualified_name}/{relative.as_posix()}")
        return buffer.getvalue()

    def import_archive(self, data: bytes, install: bool = False) -> list[Any]:
        """
        Import every plugin folder (one containing plugin.json) of a zip as
        a draft, or install it directly.
        """

        if len(data) > MAX_IMPORT_BYTES:
            raise PluginStudioError("The archive is too large.")

        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise PluginStudioError("The file is not a zip archive.") from exc

        imported: list[Any] = []

        with archive, tempfile.TemporaryDirectory(prefix="entropy-web-import-") as directory:
            root = Path(directory).resolve()
            total = 0
            for member in archive.infolist():
                target = (root / member.filename).resolve()
                # Refuse entries that escape the extraction directory.
                if root not in target.parents and target != root:
                    raise PluginStudioError(f"Unsafe path '{member.filename}' in archive.")
                total += member.file_size
                if total > MAX_IMPORT_BYTES * 5:
                    raise PluginStudioError("The archive expands too large.")
            archive.extractall(root)

            manifests = sorted(root.rglob("plugin.json"))
            if not manifests:
                raise PluginStudioError("No plugin.json found in the archive.")

            plans = []
            for manifest in manifests:
                if any(part in IGNORED_PARTS for part in manifest.parts):
                    continue
                try:
                    data_json = json.loads(manifest.read_text("utf-8"))
                    namespace = str(data_json["namespace"]).strip()
                    name = str(data_json["name"]).strip()
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    raise PluginStudioError(
                        f"{manifest.relative_to(root)} is not a valid plugin manifest."
                    ) from exc
                self.check_name(namespace, name)
                plans.append((manifest.parent, namespace, name))

            with self._lock:
                for source, namespace, name in plans:
                    destination = self._draft_path(namespace, name)
                    shutil.copytree(
                        source,
                        destination,
                        ignore=shutil.ignore_patterns(*IGNORED_PARTS),
                    )
                    imported.append(self._draft(namespace, name))

        if install:
            return [self.install(f"{item.namespace}.{item.name}") for item in imported]

        return imported

    # -- create ---------------------------------------------------------

    def create(
        self, namespace: str, name: str, description: str = "", install: bool = False
    ) -> Any:
        """
        Render the plugin template as a draft. Drafts are saved but not
        installed, so workflows cannot use them until `install`.
        """

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

            draft = self._draft_path(namespace, name)

            for template, filename in PLUGIN_FILES:
                self._context.template.render(template, draft / filename, render_context)

            for child in PLUGIN_DIRECTORIES:
                (draft / child).mkdir(parents=True, exist_ok=True)

        if install:
            return self.install(f"{namespace}.{name}")

        return self._draft(namespace, name)

    # -- read -----------------------------------------------------------

    def files(self, qualified_name: str) -> dict[str, Any]:
        plugin = self._resolve(qualified_name)
        files = read_files(plugin.path)

        return {
            "plugin": plugin,
            "files": files,
            "revision": revision(files),
        }

    # -- validate -------------------------------------------------------

    def validate(self, qualified_name: str, changes: dict[str, str]) -> list[Diagnostic]:
        plugin = self._resolve(qualified_name)
        changes = _normalize_changes(changes)

        with tempfile.TemporaryDirectory(prefix="entropy-web-plugin-") as directory:
            return self._diagnostics(plugin, changes, Path(directory))

    def _diagnostics(
        self,
        plugin: Any,
        changes: dict[str, str],
        directory: Path,
        removed: Sequence[str] = (),
    ) -> list[Diagnostic]:
        staged = _stage(plugin.path, directory / plugin.name, changes, removed)
        files = {**read_files(plugin.path), **changes}
        for path in removed:
            files.pop(path, None)

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
        install: bool = False,
        backup: Optional[Backup] = None,
        removed: Sequence[str] = (),
    ) -> dict[str, Any]:
        """
        Apply changed files (and remove `removed` ones). `backup` receives the
        files being replaced once the change is known to be valid.
        """

        changes = _normalize_changes(changes)
        removed = [normalize_path(path) for path in removed]
        plugin = self._resolve(qualified_name)

        if getattr(plugin, "draft", False):
            return self._save_draft(plugin, changes, base_revision, install, backup, removed)

        with self._lock:
            plugin = self._manager.get(qualified_name)

            current = read_files(plugin.path)
            if revision(current) != base_revision:
                raise PluginConflictError(
                    f"Plugin '{qualified_name}' changed since it was opened. "
                    "Reload it and reapply your edits."
                )

            changes = self._bump_on_change(current, changes)

            with tempfile.TemporaryDirectory(prefix="entropy-web-plugin-") as directory:
                root = Path(directory)
                source = root / "source"
                source.mkdir()

                diagnostics = self._diagnostics(plugin, changes, source, removed)

                if any(item.severity == "error" for item in diagnostics):
                    raise PluginValidationFailed(diagnostics)

                if backup is not None and self._changes(current, changes, removed):
                    backup(current, _manifest_version(current))

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

    @staticmethod
    def _bump_on_change(current: dict[str, str], changes: dict[str, str]) -> dict[str, str]:
        """
        Editing an installed plugin raises its patch version unless the
        author changed the version themselves.
        """

        effective = {
            path: content for path, content in changes.items() if current.get(path) != content
        }
        manifest = changes.get("plugin.json", current.get("plugin.json", ""))
        old = MANIFEST_VERSION.search(current.get("plugin.json", ""))
        new = MANIFEST_VERSION.search(manifest)

        if not effective or old is None or new is None or old.group(2) != new.group(2):
            return changes

        bumped = MANIFEST_VERSION.sub(
            lambda match: match.group(1) + bump_version(match.group(2)) + match.group(3),
            manifest,
            count=1,
        )
        return {**changes, "plugin.json": bumped}

    @staticmethod
    def _changes(current: dict[str, str], changes: dict[str, str], removed: Sequence[str]) -> bool:
        return any(current.get(path) != content for path, content in changes.items()) or any(
            path in current for path in removed
        )

    def _save_draft(
        self,
        draft: Any,
        changes: dict[str, str],
        base_revision: str,
        install: bool,
        backup: Optional[Backup] = None,
        removed: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Drafts keep work in progress even when it does not validate yet."""

        qualified_name = f"{draft.namespace}.{draft.name}"

        with self._lock:
            current = read_files(draft.path)
            if revision(current) != base_revision:
                raise PluginConflictError(
                    f"Draft '{qualified_name}' changed since it was opened. "
                    "Reload it and reapply your edits."
                )

            if "plugin.json" in changes:
                with tempfile.TemporaryDirectory(prefix="entropy-web-plugin-") as directory:
                    staged = _stage(draft.path, Path(directory) / draft.name, changes)
                    # The folder name is fixed; the manifest must keep matching it.
                    identity = check_manifest(
                        staged, draft.namespace, draft.name, self._reader, self._validator
                    )
                if identity:
                    raise PluginValidationFailed(identity)

            if backup is not None and self._changes(current, changes, removed):
                backup(current, _manifest_version(current))

            for path in removed:
                with contextlib.suppress(FileNotFoundError):
                    (draft.path / path).unlink()

            for path, content in changes.items():
                target = draft.path / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

        if install:
            self.install(qualified_name)

        return self.files(qualified_name)

    # -- restore --------------------------------------------------------

    def restore(
        self, qualified_name: str, files: dict[str, str], backup: Optional[Backup] = None
    ) -> dict[str, Any]:
        """
        Make an earlier version's files current again, under the next version
        number. Goes through the same checks as an edit.
        """

        plugin = self._resolve(qualified_name)
        current = read_files(plugin.path)
        files = dict(files)

        version = _manifest_version(current)
        if version and "plugin.json" in files:
            files["plugin.json"] = MANIFEST_VERSION.sub(
                lambda match: match.group(1) + bump_version(version) + match.group(3),
                files["plugin.json"],
                count=1,
            )

        removed = [path for path in current if path not in files]
        return self.save(
            qualified_name, files, revision(current), backup=backup, removed=removed
        )

    # -- delete ---------------------------------------------------------

    def delete(self, qualified_name: str) -> None:
        plugin = self._resolve(qualified_name)

        with self._lock:
            if getattr(plugin, "draft", False):
                shutil.rmtree(plugin.path, ignore_errors=True)
                with contextlib.suppress(OSError):
                    plugin.path.parent.rmdir()
                return

            self._manager.uninstall(qualified_name)
