"""Plugin contracts: declared arguments and outputs, checked at install and run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.models.plugin import PluginResult
from lib.plugins import contract
from lib.plugins.base import BasePlugin
from lib.plugins.contract import ContractError
from lib.plugins.exceptions import PluginExecutionError
from lib.plugins.runner import PluginRunner

BUNDLED = Path(__file__).resolve().parents[2] / "resources" / "plugins"

DECLARED = {
    "arguments": [
        {"name": "host", "type": "string", "required": True},
        {"name": "port", "type": "integer", "default": 22, "minimum": 1, "maximum": 65535},
        {"name": "mode", "choices": ["get", "put"], "default": "get"},
        {"name": "password", "secret": True},
        {"name": "verbose", "type": "boolean", "default": False},
        {"name": "source", "type": "path", "path": "file"},
    ],
    "outputs": ["transferred", {"name": "files", "type": "list"}],
}


def test_normalize_fills_defaults_and_refuses_bad_declarations() -> None:
    normal = contract.normalize(DECLARED)
    names = [item["name"] for item in normal["arguments"]]
    assert names == ["host", "port", "mode", "password", "verbose", "source"]
    host, port = normal["arguments"][:2]
    assert host["required"] and host["type"] == "string" and not host["secret"]
    assert (port["minimum"], port["maximum"]) == (1, 65535)
    assert normal["arguments"][3]["secret"] is True
    assert normal["arguments"][5]["path"] == "file"
    assert normal["outputs"][0] == {"name": "transferred", "type": "any", "description": ""}

    with pytest.raises(ContractError) as caught:
        contract.normalize(
            {
                "arguments": [
                    {"name": "bad name"},
                    {"name": "a", "type": "colour"},
                    {"name": "b", "required": True, "default": "x"},
                    {"name": "c", "type": "integer", "default": "ten"},
                    {"name": "d", "unexpected": 1},
                    {"name": "e"},
                    {"name": "e"},
                ],
                "outputs": "nope",
            }
        )
    text = "; ".join(caught.value.problems)
    for expected in (
        "Python-style identifier",
        "type must be one of",
        "required argument has no default",
        "default is not a integer",
        "unknown keys unexpected",
        "'e' is declared twice",
        '"outputs" must be a list',
    ):
        assert expected in text


def test_declared_is_none_for_plugins_from_before_contracts() -> None:
    assert contract.declared({"name": "old"}) is None
    assert contract.declared({"arguments": [], "outputs": []}) == {"arguments": [], "outputs": []}


def test_check_arguments_coerces_fills_defaults_and_reports_every_problem() -> None:
    normal = contract.normalize(DECLARED)
    checked = contract.check_arguments(normal, {"host": "db1", "port": "2222", "verbose": "yes"})
    assert checked == {"host": "db1", "port": 2222, "mode": "get", "verbose": True}
    assert contract.check_arguments(normal, {"host": "db1", "mode": "PUT"})["mode"] == "put"
    # Workflow references are resolved later; they pass as they are.
    assert contract.check_arguments(normal, {"host": "${inputs.host}", "port": "${p}"})["port"] == (
        "${p}"
    )

    with pytest.raises(ContractError) as caught:
        contract.check_arguments(
            normal, {"port": 0, "mode": "delete", "colour": "red", "verbose": "maybe"}
        )
    problems = caught.value.problems
    assert any("unknown argument colour" in item for item in problems)
    assert "'host' is required" in problems
    assert "'port' must be at least 1" in problems
    assert "'mode' must be one of get, put" in problems
    assert "'verbose' must be a boolean" in problems


def test_check_outputs_refuses_undeclared_names() -> None:
    normal = contract.normalize(DECLARED)
    assert contract.check_outputs(normal, {"transferred": 3, "files": []}) == []
    assert contract.check_outputs(normal, {"extra": 1}) == [
        "output 'extra' is not declared in plugin.json"
    ]


def _plugin(tmp_path: Path, source: str, manifest: dict) -> Path:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "plugin.py").write_text(source, encoding="utf-8")
    (folder / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


SOURCE = """
from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin


class Demo(BasePlugin):
    def execute(self):
        host = self.arguments.get("host")
        level = self.arguments.get("level", 1)
        self.outputs["reached"] = host
        return PluginResult(success=True, outputs={"level": level})
"""


def test_check_source_finds_undeclared_reads_and_outputs(tmp_path) -> None:
    folder = _plugin(
        tmp_path,
        SOURCE,
        {"arguments": [{"name": "host"}], "outputs": ["reached"]},
    )
    manifest = contract.read_manifest(folder)
    problems = contract.check_source(folder, contract.declared(manifest))
    assert problems == [
        "the source reads argument 'level', which is not declared",
        "the source publishes output 'level', which is not declared",
    ]
    inferred = contract.inferred(folder)
    assert {item["name"] for item in inferred["arguments"]} == {"host", "level"}

    full = {"arguments": [{"name": "host"}, {"name": "level"}], "outputs": ["level", "reached"]}
    assert contract.check_source(folder, contract.normalize(full)) == []

    (folder / "plugin.py").write_text("class Nothing:\n    pass\n", encoding="utf-8")
    assert contract.check_source(folder, contract.normalize(full)) == [
        "plugin.py has no class based on BasePlugin"
    ]


def test_plugin_contract_prefers_the_declared_one(tmp_path) -> None:
    folder = _plugin(tmp_path, SOURCE, {"description": "Demo"})
    assert contract.plugin_contract(folder)["contract"] == "inferred"
    (folder / "plugin.json").write_text(
        json.dumps({"arguments": [{"name": "host", "required": True}], "outputs": []}),
        encoding="utf-8",
    )
    described = contract.plugin_contract(folder)
    assert described["contract"] == "declared"
    assert [item["name"] for item in described["arguments"]] == ["host"]


class _Recorder(BasePlugin):
    def __init__(self, calls, fail=None, outputs=None):  # noqa: D107 - no context needed
        self.calls = calls
        self.fail = fail
        self.result_outputs = outputs or {}

    def _step(self, name):
        self.calls.append(name)
        if self.fail == name:
            raise RuntimeError(name)

    def validate(self):
        self._step("validate")

    def prepare(self):
        self._step("prepare")

    def execute(self):
        self._step("execute")
        return PluginResult(success=True, outputs=self.result_outputs)

    def cleanup(self):
        self._step("cleanup")


def test_lifecycle_runs_in_order_and_always_cleans_up() -> None:
    calls: list = []
    PluginRunner._lifecycle(_Recorder(calls), "demo")
    assert calls == ["validate", "prepare", "execute", "cleanup"]

    for failing in ("validate", "prepare", "execute"):
        calls = []
        with pytest.raises(RuntimeError):
            PluginRunner._lifecycle(_Recorder(calls, fail=failing), "demo")
        assert calls[-1] == "cleanup" and failing in calls


def test_lifecycle_refuses_undeclared_outputs() -> None:
    plugin = _Recorder([], outputs={"ok": 1, "stray": 2})
    plugin._entropy_contract = contract.normalize({"arguments": [], "outputs": ["ok"]})
    with pytest.raises(PluginExecutionError, match="output 'stray' is not declared"):
        PluginRunner._lifecycle(plugin, "demo")


@pytest.mark.parametrize(
    "folder",
    sorted(path.parent for path in BUNDLED.glob("*/*/plugin.json")),
    ids=lambda path: f"{path.parent.name}.{path.name}",
)
def test_every_bundled_plugin_keeps_its_contract(folder: Path) -> None:
    manifest = contract.read_manifest(folder)
    declared = contract.declared(manifest)
    assert declared is not None, "plugin.json declares no arguments/outputs"
    assert contract.check_source(folder, declared) == []
    for example in sorted(folder.glob("*workflow*.json")):
        steps = json.loads(example.read_text(encoding="utf-8")).get("steps") or []
        for step in steps:
            if step.get("plugin", "").endswith(f"{folder.parent.name}.{folder.name}"):
                contract.check_arguments(declared, step.get("arguments") or {})


def _choices_plugin(tmp_path: Path, choices_from: dict) -> Path:
    (tmp_path / "plugin.json").write_text(
        json.dumps(
            {
                "arguments": [
                    {"name": "country", "type": "string", "choices_from": choices_from},
                ],
                "outputs": [],
            },
        ),
        encoding="utf-8",
    )
    (tmp_path / "mapping.json").write_text(
        json.dumps({"countries": {"IN": {}, "SG": {}}, "nested": {"list": ["a", "b"]}}),
        encoding="utf-8",
    )
    return tmp_path


def test_choices_from_reads_keys_of_a_file_in_the_plugin(tmp_path) -> None:
    folder = _choices_plugin(tmp_path, {"file": "mapping.json", "key": "countries"})
    declared = contract.declared(contract.read_manifest(folder))

    assert declared["arguments"][0]["choices"] == ["IN", "SG"]
    assert contract.check_arguments(declared, {"country": "in"})["country"] == "IN"
    with pytest.raises(ContractError):
        contract.check_arguments(declared, {"country": "UK"})

    # A new entry in the file is offered on the next read.
    (folder / "mapping.json").write_text(
        json.dumps({"countries": {"IN": {}, "SG": {}, "UK": {}}}),
        encoding="utf-8",
    )
    declared = contract.declared(contract.read_manifest(folder))
    assert contract.check_arguments(declared, {"country": "UK"})["country"] == "UK"


def test_choices_from_reads_list_items_at_a_dot_path(tmp_path) -> None:
    folder = _choices_plugin(tmp_path, {"file": "mapping.json", "key": "nested.list"})

    assert contract.declared(contract.read_manifest(folder))["arguments"][0]["choices"] == [
        "a",
        "b",
    ]


@pytest.mark.parametrize(
    "source",
    [
        {"file": "missing.json", "key": "countries"},
        {"file": "mapping.json", "key": "nothing.here"},
        {"file": "../outside.json", "key": "countries"},
    ],
)
def test_choices_from_without_a_value_leaves_the_argument_free(tmp_path, source) -> None:
    (tmp_path.parent / "outside.json").write_text('{"countries": {"X": 1}}', encoding="utf-8")
    folder = _choices_plugin(tmp_path, source)
    declared = contract.declared(contract.read_manifest(folder))

    assert "choices" not in declared["arguments"][0]
    assert contract.check_arguments(declared, {"country": "anything"})["country"] == "anything"


def test_choices_from_must_be_well_formed() -> None:
    with pytest.raises(ContractError, match="choices_from"):
        contract.normalize(
            {
                "arguments": [{"name": "country", "choices_from": "mapping.json"}],
                "outputs": [],
            },
        )
