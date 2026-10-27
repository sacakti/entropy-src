"""Tests for browser plugin development: SDK analysis and staged saves."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.web.plugin_studio.analysis import check_files
from core.web.plugin_studio.sdk import build_catalog
from core.web.plugin_studio.workspace import (
    PluginConflictError,
    PluginStudio,
    PluginStudioError,
    PluginValidationFailed,
    normalize_path,
    read_files,
    revision,
)
from lib.models.plugin import Plugin

PLUGIN = """
from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import DemoException


class DemoPlugin(BasePlugin):
    def execute(self) -> PluginResult:
        name = self.arguments.string("name", "world")
        self.message.info(f"Hello {name}")
        return PluginResult(outputs=dict(self.outputs))
"""

EXCEPTIONS = """
from lib.plugins.exceptions import PluginException


class DemoException(PluginException):
    pass
"""

MANIFEST = {
    "name": "demo",
    "namespace": "custom",
    "version": "1.0.0",
    "entropy": ">=1.0.0",
    # Plugins declare what they take and publish (lib/plugins/contract.py).
    "arguments": [{"name": "name", "type": "string", "default": "world"}],
    "outputs": [],
}


def messages(files: dict[str, str]) -> list[str]:
    return [item.message for item in check_files(files)]


# ----------------------------------------------------------------------
# SDK catalog
# ----------------------------------------------------------------------


def test_catalog_describes_plugin_sdk() -> None:
    catalog = build_catalog()
    root = {member["name"]: member for member in catalog["types"]["BasePlugin"]["members"]}

    assert root["arguments"]["type"] == "PluginArguments"
    assert root["message"]["type"] == "PluginMessage"
    assert "string" in {member["name"] for member in catalog["types"]["PluginArguments"]["members"]}
    assert "PluginResult" in {symbol["name"] for symbol in catalog["symbols"]}


# ----------------------------------------------------------------------
# Analysis
# ----------------------------------------------------------------------


def test_valid_plugin_has_no_diagnostics() -> None:
    assert check_files({"plugin.py": PLUGIN, "exceptions.py": EXCEPTIONS}) == []


def test_reports_unknown_sdk_members_and_attributes() -> None:
    source = PLUGIN.replace("self.arguments.string", "self.arguments.dict").replace(
        "self.message.info", "self.missing.info"
    )

    found = messages({"plugin.py": source, "exceptions.py": EXCEPTIONS})

    assert "'dict' is not a member of self.arguments (PluginArguments)." in found
    assert "'missing' is not defined on DemoPlugin or the Plugin SDK." in found


def test_reports_undefined_names_by_scope() -> None:
    source = """
LIMIT = 3
value = self.arguments


class Example:
    size = 1

    def run(self, item):
        squares = [n * n for n in range(LIMIT)]
        return size, squares, item, unknown
"""

    found = messages({"example.py": source})

    assert found == [
        "Undefined name 'self'.",
        "Undefined name 'size'.",
        "Undefined name 'unknown'.",
    ]


def test_reports_broken_imports() -> None:
    source = PLUGIN.replace(
        "from .exceptions import DemoException",
        "from .exceptions import Missing\nfrom .engine import Engine",
    ).replace("import PluginResult", "import PluginResult, Nope")

    found = messages({"plugin.py": source, "exceptions.py": EXCEPTIONS})

    assert "'Missing' is not defined in plugin module 'exceptions'." in found
    assert "Plugin module 'engine' was not found." in found
    assert "'Nope' is not exported by 'lib.models.plugin'." in found


def test_resolves_subpackages_and_skips_cross_plugin_imports() -> None:
    files = {
        "plugin.py": "from .ops import run\nfrom ..generic.executor import Executor\n",
        "ops/__init__.py": "from .runner import run\n",
        "ops/runner.py": "def run():\n    pass\n",
    }

    assert check_files(files) == []


def test_reports_syntax_and_json_errors_with_positions() -> None:
    diagnostics = check_files({"plugin.py": "def broken(:\n", "plugin.json": '{"a": }'})

    assert [(item.path, item.source, item.line) for item in diagnostics] == [
        ("plugin.json", "json", 1),
        ("plugin.py", "syntax", 1),
    ]


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "../evil.py",
        "/etc/passwd.py",
        "a/../../b.py",
        "script.sh",
        "__pycache__/x.py",
        ".hidden.py",
        "",
    ],
)
def test_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(PluginStudioError):
        normalize_path(path)


def test_accepts_plugin_relative_paths() -> None:
    assert normalize_path("ops/runner.py") == "ops/runner.py"
    assert normalize_path(" README.md ") == "README.md"
    assert normalize_path("data/hosts.csv") == "data/hosts.csv"


# ----------------------------------------------------------------------
# Save
# ----------------------------------------------------------------------


class FakeExecutor:
    def exists(self, path: Path) -> bool:
        return path.exists()

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))


class FakeManager:
    """Installs by copying a staged directory, like PluginInstaller."""

    def __init__(self, root: Path, fail_repair: bool = False) -> None:
        self.root = root
        self.fail_repair = fail_repair
        self.plugins: dict[str, Plugin] = {}
        self.disabled: list[str] = []

    def install(self, source: Path) -> Plugin:
        import shutil

        manifest = json.loads((source / "plugin.json").read_text())
        destination = self.root / manifest["namespace"] / manifest["name"]
        shutil.copytree(source, destination)
        plugin = Plugin(
            manifest["namespace"], manifest["name"], manifest["version"], destination, id=1
        )
        self.plugins[plugin.qualified_name] = plugin
        return plugin

    def uninstall(self, qualified_name: str) -> None:
        import shutil

        shutil.rmtree(self.plugins.pop(qualified_name).path)

    def repair(self, qualified_name: str, source: Path) -> None:
        self.uninstall(qualified_name)

        if self.fail_repair:
            raise RuntimeError("migration failed")

        self.install(source)

    def get(self, qualified_name: str) -> Plugin:
        return self.plugins[qualified_name]

    def exists(self, qualified_name: str) -> bool:
        return qualified_name in self.plugins

    def disable(self, qualified_name: str) -> None:
        self.disabled.append(qualified_name)


def make_studio(tmp_path: Path, fail_repair: bool = False) -> tuple[PluginStudio, FakeManager]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "plugin.py").write_text(PLUGIN)
    (source / "exceptions.py").write_text(EXCEPTIONS)
    (source / "plugin.json").write_text(json.dumps(MANIFEST))

    manager = FakeManager(tmp_path / "installed", fail_repair=fail_repair)
    manager.install(source)

    context = SimpleNamespace(plugin_manager=manager, executor=FakeExecutor())
    return PluginStudio(context), manager


def test_save_reinstalls_with_changes(tmp_path: Path) -> None:
    studio, manager = make_studio(tmp_path)
    current = studio.files("custom.demo")
    edited = PLUGIN.replace("Hello", "Hi")

    result = studio.save(
        "custom.demo", {"plugin.py": edited, "engine.py": "X = 1\n"}, current["revision"]
    )

    installed = read_files(manager.get("custom.demo").path)
    assert installed["plugin.py"] == edited
    assert installed["engine.py"] == "X = 1\n"
    assert result["revision"] == revision(installed)


def test_save_keeps_csv_files(tmp_path: Path) -> None:
    studio, manager = make_studio(tmp_path)
    current = studio.files("custom.demo")
    table = 'host;port\r\n"a;b";22\r\n'

    studio.save("custom.demo", {"data/hosts.csv": table}, current["revision"])

    root = manager.get("custom.demo").path
    assert (root / "data" / "hosts.csv").read_bytes() == table.encode()
    assert studio.files("custom.demo")["files"]["data/hosts.csv"] == table


def test_save_rejects_stale_revision(tmp_path: Path) -> None:
    studio, _ = make_studio(tmp_path)

    with pytest.raises(PluginConflictError):
        studio.save("custom.demo", {"plugin.py": PLUGIN}, "stale")


def test_save_rejects_invalid_changes_without_touching_install(tmp_path: Path) -> None:
    studio, manager = make_studio(tmp_path)
    current = studio.files("custom.demo")
    renamed = json.dumps({**MANIFEST, "name": "other"})

    with pytest.raises(PluginValidationFailed) as failure:
        studio.save("custom.demo", {"plugin.json": renamed}, current["revision"])

    assert failure.value.diagnostics[0].path == "plugin.json"
    assert read_files(manager.get("custom.demo").path) == current["files"]


def test_failed_reinstall_restores_previous_installation(tmp_path: Path) -> None:
    studio, manager = make_studio(tmp_path, fail_repair=True)
    current = studio.files("custom.demo")

    with pytest.raises(RuntimeError, match="migration failed"):
        studio.save("custom.demo", {"plugin.py": PLUGIN + "\n"}, current["revision"])

    assert manager.exists("custom.demo")
    assert read_files(manager.get("custom.demo").path) == current["files"]


def test_save_moves_files_and_keeps_line_endings(tmp_path: Path) -> None:
    studio, manager = make_studio(tmp_path)
    current = studio.files("custom.demo")
    windows = "X = 1\r\nY = 2\r\n"
    saved = studio.save("custom.demo", {"tools.py": windows}, current["revision"])

    # A move is the new path plus the old one removed.
    studio.save(
        "custom.demo",
        {"helpers/tools.py": windows},
        saved["revision"],
        removed=["tools.py"],
    )

    root = manager.get("custom.demo").path
    assert not (root / "tools.py").exists()
    assert (root / "helpers" / "tools.py").read_bytes() == windows.encode()
    assert read_files(root)["helpers/tools.py"] == windows
    # Validation sees the same removals.
    assert studio.validate("custom.demo", {}, removed=["helpers/tools.py"]) == []
