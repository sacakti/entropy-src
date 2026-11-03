"""Command line tools plugins need, as plugin.json declares them and people see them."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.web.plugin_studio.docs import plugin_docs
from core.web.routes.plugins import _manifest_dependencies
from lib.plugins import requirements
from lib.plugins.requirements import system_requirements, tool_available

PLUGINS = Path(__file__).resolve().parents[2] / "resources" / "plugins"

# From each plugin's code: the tools it runs itself. A plugin that only writes or reads
# a command as text (consolidate.images, release.context_builder) needs nothing.
EXPECTED = {
    "builtin.git": ["git"],
    "builtin.process_monitor": ["ps"],
    "custom.cache_refresh": ["oc"],
    "custom.image_transfer": ["docker"],
    "custom.load_data": ["sqlplus"],
    "docker.build": ["docker"],
    "docker.clean": ["docker"],
    "docker.generic": ["docker"],
    "oc.audit": ["git"],
    "oc.generic": ["oc"],
    "oc.pod_metrics": ["oc"],
    "oc.rsync": ["oc"],
    "oc.sync_yamls": ["oc"],
    "skopeo.generic": ["skopeo", "oc"],
    "sqlplus.generic": ["sqlplus"],
}


def _bundled():
    for path in sorted(PLUGINS.glob("*/*/plugin.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        yield f"{manifest['namespace']}.{manifest['name']}", manifest


def test_every_bundled_plugin_declares_the_tools_it_runs() -> None:
    declared = {
        name: [item["name"] for item in manifest["system_requirements"]]
        for name, manifest in _bundled()
        if manifest.get("system_requirements")
    }

    assert declared == EXPECTED


def test_declared_entries_are_named_and_described() -> None:
    for name, manifest in _bundled():
        for item in manifest.get("system_requirements", []):
            assert set(item) <= {"name", "note", "optional"}, name
            assert item["name"] and item["note"], name


@pytest.mark.parametrize(
    "value",
    [None, "oc", 3, {"name": "oc"}, [None], [3], [{}], [{"name": 3}], [{"name": "  "}], [""]],
)
def test_malformed_declarations_are_left_out(value) -> None:
    assert system_requirements({"system_requirements": value}) == []


def test_a_plain_name_and_a_full_entry_are_both_understood(monkeypatch) -> None:
    monkeypatch.setattr(requirements, "tool_available", lambda name: name == "oc")

    tools = system_requirements(
        {"system_requirements": ["oc", {"name": "git", "optional": True, "note": "Sometimes."}]}
    )

    assert tools == [
        {"name": "oc", "optional": False, "note": "", "available": True},
        {"name": "git", "optional": True, "note": "Sometimes.", "available": False},
    ]


def test_availability_comes_from_the_path(monkeypatch) -> None:
    monkeypatch.setattr(
        requirements.shutil, "which", lambda name: "/bin/x" if name == "oc" else None
    )
    monkeypatch.delenv("ORACLE_HOME", raising=False)

    assert tool_available("oc") is True
    assert tool_available("docker") is False


def test_sqlplus_may_be_in_oracle_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(requirements.shutil, "which", lambda name: None)
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))

    assert tool_available("sqlplus") is False

    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "sqlplus").write_text("")

    assert tool_available("sqlplus") is True
    assert tool_available("oc") is False


def test_the_plugin_list_reports_tools_beside_libraries_and_plugins(tmp_path) -> None:
    (tmp_path / "plugin.json").write_text(
        json.dumps(
            {
                "dependencies": [{"name": "paramiko", "version": "3.0"}],
                "required_plugins": ["oc.generic"],
                "system_requirements": [{"name": "oc", "note": "Client."}],
            }
        )
    )

    found = _manifest_dependencies(tmp_path)

    assert found["extensions"] == [{"name": "paramiko", "version": "3.0"}]
    assert found["plugins"] == [{"name": "oc.generic"}]
    assert [item["name"] for item in found["tools"]] == ["oc"]


def test_a_plugin_with_an_unreadable_manifest_needs_nothing(tmp_path) -> None:
    assert _manifest_dependencies(tmp_path)["tools"] == []


def test_the_plugin_help_reports_tools(tmp_path) -> None:
    (tmp_path / "plugin.json").write_text(
        json.dumps({"system_requirements": [{"name": "oc", "note": "Client.", "optional": True}]})
    )
    plugin = SimpleNamespace(path=tmp_path, namespace="oc", name="thing")

    [tool] = plugin_docs(plugin, None)["system_requirements"]

    assert (tool["name"], tool["note"], tool["optional"]) == ("oc", "Client.", True)
