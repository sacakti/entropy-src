"""Tests for recovering plugin arguments and outputs from source."""

from __future__ import annotations

from pathlib import Path

from core.web.plugin_studio.contract import plugin_contract

PLUGIN = """
from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin


class DemoPlugin(BasePlugin):
    def execute(self) -> PluginResult:
        source = self.arguments.path("source", required=True)
        mode = self.arguments.string("mode", "copy")
        retries = self.arguments.integer("retries", default=3, minimum=0, maximum=10)
        token = self.arguments.required("token")
        dynamic = self.arguments.string(self.name)
        self.outputs["copied"] = 1
        self.outputs.update({"source": str(source)}, mode=mode)
        return PluginResult(outputs={"retries": retries, **self.outputs})
"""

HELPER = """
def configure(context):
    arguments = context.arguments
    return arguments.boolean("dry_run", False)
"""


def write_plugin(tmp_path: Path) -> Path:
    (tmp_path / "plugin.json").write_text('{"description": "Demo plugin"}')
    (tmp_path / "plugin.py").write_text(PLUGIN)
    (tmp_path / "helper.py").write_text(HELPER)
    return tmp_path


def test_extracts_typed_arguments(tmp_path: Path) -> None:
    contract = plugin_contract(write_plugin(tmp_path))
    arguments = {item["name"]: item for item in contract["arguments"]}

    assert contract["description"] == "Demo plugin"
    assert set(arguments) == {"source", "mode", "retries", "token", "dry_run"}
    assert arguments["source"] == {
        "name": "source",
        "type": "path",
        "required": True,
        "default": None,
    }
    assert arguments["mode"]["default"] == "copy"
    assert arguments["retries"]["minimum"] == 0
    assert arguments["retries"]["maximum"] == 10
    assert arguments["token"]["required"] is True
    assert arguments["dry_run"] == {
        "name": "dry_run",
        "type": "boolean",
        "required": False,
        "default": False,
    }
    # Required arguments are listed first.
    assert [item["required"] for item in contract["arguments"]][:2] == [True, True]


def test_extracts_outputs(tmp_path: Path) -> None:
    contract = plugin_contract(write_plugin(tmp_path))

    assert contract["outputs"] == ["copied", "mode", "retries", "source"]


def test_ignores_unparseable_sources(tmp_path: Path) -> None:
    (tmp_path / "plugin.py").write_text("def broken(:\n")

    assert plugin_contract(tmp_path) == {
        "description": None,
        "contract": "inferred",
        "arguments": [],
        "outputs": [],
        "output_details": [],
    }
