"""
Tests for consolidate.cm_secret: consolidation rules and the plugin over
real release packages (ZIPs and folders, standard and App-Published layouts).
"""

from __future__ import annotations

import json
import zipfile
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest
import yaml

from lib.executor import LinuxExecutor
from lib.plugins import contract
from lib.plugins.arguments import PluginArguments
from resources.plugins.consolidate.cm_secret.consolidator import Consolidator, Source
from resources.plugins.consolidate.cm_secret.exceptions import ConsolidationDefinitionError
from resources.plugins.consolidate.cm_secret.plugin import (
    ConsolidateCmSecretPlugin,
    natural_key,
)

PLUGIN_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "resources" / "plugins" / "consolidate" / "cm_secret"
)


def update(name: str, *operations: Dict[str, Any], kind: str = "ConfigMap") -> Dict[str, Any]:
    return {
        "apiVersion": "entropy/v1",
        "kind": "ConfigMapSecretUpdate",
        "target": {"kind": kind, "name": name},
        "operations": list(operations),
    }


def native(name: str, data: Dict[str, Any], kind: str = "ConfigMap") -> Dict[str, Any]:
    return {"apiVersion": "v1", "kind": kind, "metadata": {"name": name}, "data": data}


def consolidate(*releases: List[Dict[str, Any]]) -> Consolidator:
    consolidator = Consolidator()
    for number, documents in enumerate(releases, start=1):
        for document in documents:
            consolidator.add(document, Source(release=f"H{number:03d}", file="x.yaml"))
    return consolidator


def documents(consolidator: Consolidator, name: str = "cm-app") -> List[Dict[str, Any]]:
    [target] = [item for item in consolidator.targets if item.name == name]
    return target.documents()


def operations(consolidator: Consolidator, name: str = "cm-app") -> List[Dict[str, Any]]:
    [document] = documents(consolidator, name)
    return document["operations"]


# ----------------------------------------------------------------------
# Plain values
# ----------------------------------------------------------------------


def test_later_release_wins_and_delete_cancels() -> None:
    result = consolidate(
        [update("cm-app", {"action": "update", "key": "db.url", "value": "A"})],
        [
            update(
                "cm-app",
                {"action": "update", "key": "db.url", "value": "B"},
                {"action": "add", "key": "feature.x", "value": "on"},
            )
        ],
        [update("cm-app", {"action": "delete", "key": "feature.x"})],
    )

    assert operations(result) == [
        {"action": "update", "key": "db.url", "value": "B"},
        {"action": "delete", "key": "feature.x"},
    ]
    [target] = result.targets
    assert target.last_changed == {"db.url": "H002", "feature.x": "H003"}
    assert [source.release for source in target.sources] == ["H001", "H002", "H003"]


def test_add_after_delete_revives_the_key() -> None:
    result = consolidate(
        [update("cm-app", {"action": "delete", "key": "k"})],
        [update("cm-app", {"action": "add", "key": "k", "value": 1})],
    )

    assert operations(result) == [{"action": "add", "key": "k", "value": 1}]


def test_targets_are_kept_apart() -> None:
    result = consolidate(
        [
            update("cm-app", {"action": "update", "key": "a", "value": "1"}),
            update("cm-app", {"action": "update", "key": "a", "value": "S"}, kind="Secret"),
        ]
    )

    assert sorted((target.kind, target.name) for target in result.targets) == [
        ("ConfigMap", "cm-app"),
        ("Secret", "cm-app"),
    ]


# ----------------------------------------------------------------------
# Structured values
# ----------------------------------------------------------------------


def test_properties_entries_merge_and_deletes_cancel() -> None:
    def props(action: str, entries: Any) -> Dict[str, Any]:
        key = "app.properties"
        return {"action": action, "key": key, "format": "properties", "entries": entries}

    result = consolidate(
        [update("cm-app", props("update", {"a": "1", "b": "1"}))],
        [update("cm-app", props("update", {"a": "2", "c": "3"}))],
        [update("cm-app", props("delete", ["b", "c", "gone"]))],
        [update("cm-app", props("update", {"gone": "back"}))],
    )

    assert operations(result) == [
        props("delete", ["b", "c"]),
        props("update", {"a": "2", "gone": "back"}),
    ]


def test_yaml_paths_merge_deeply() -> None:
    def tree(action: str, entries: Any) -> Dict[str, Any]:
        return {"action": action, "key": "app.yaml", "format": "yaml", "entries": entries}

    result = consolidate(
        [update("cm-app", tree("update", {"server": {"port": 80, "host": "h"}, "x": 1}))],
        [update("cm-app", tree("update", {"server": {"port": 8080}}))],
        [update("cm-app", tree("delete", ["server.host", "x"]))],
        [update("cm-app", tree("update", {"x": {"y": 2}}))],
    )

    assert operations(result) == [
        tree("delete", ["server.host", "x"]),
        tree("update", {"server": {"port": 8080}, "x": {"y": 2}}),
    ]


def test_a_mapping_written_below_an_earlier_plain_value_removes_it_first() -> None:
    def tree(entries: Any) -> Dict[str, Any]:
        return {"action": "update", "key": "app.json", "format": "json", "entries": entries}

    result = consolidate(
        [update("cm-app", tree({"a": 5}))],
        [update("cm-app", tree({"a": {"b": 1}}))],
    )

    # In sequence a=5 is replaced by {b: 1}: delete a, then write a.b.
    assert operations(result) == [
        {"action": "delete", "key": "app.json", "format": "json", "entries": ["a"]},
        tree({"a": {"b": 1}}),
    ]


def test_a_plain_value_replaces_earlier_structured_changes() -> None:
    result = consolidate(
        [
            update(
                "cm-app",
                {"action": "update", "key": "p", "format": "properties", "entries": {"a": "1"}},
            )
        ],
        [update("cm-app", {"action": "update", "key": "p", "value": "a=9\n"})],
    )

    assert operations(result) == [{"action": "update", "key": "p", "value": "a=9\n"}]


def test_different_formats_stay_in_order() -> None:
    result = consolidate(
        [update("cm-app", {"action": "update", "key": "k", "format": "yaml", "entries": {"a": 1}})],
        [update("cm-app", {"action": "update", "key": "k", "format": "json", "entries": {"b": 2}})],
    )

    assert [operation["format"] for operation in operations(result)] == ["yaml", "json"]


# ----------------------------------------------------------------------
# Native resources
# ----------------------------------------------------------------------


def test_native_resources_merge_and_keep_their_place_in_the_sequence() -> None:
    result = consolidate(
        [native("cm-app", {"a": "1", "b": "1"})],
        [native("cm-app", {"b": "2"})],
        [update("cm-app", {"action": "delete", "key": "a"})],
        [native("cm-app", {"c": "3"})],
    )

    assert documents(result) == [
        native("cm-app", {"a": "1", "b": "2"}),
        update("cm-app", {"action": "delete", "key": "a"}),
        native("cm-app", {"c": "3"}),
    ]


def test_other_resources_are_ignored() -> None:
    consolidator = Consolidator()

    assert not consolidator.add(
        {"apiVersion": "apps/v1", "kind": "Deployment"}, Source("H001", "d.yaml")
    )
    assert consolidator.targets == [] and consolidator.ignored == 1


@pytest.mark.parametrize(
    "document, message",
    [
        (update("cm-app"), "non-empty list"),
        ({**update("cm-app"), "target": {"kind": "Route", "name": "r"}}, "ConfigMap or Secret"),
        (update("cm-app", {"action": "rename", "key": "a"}), "unsupported operation"),
        (update("cm-app", {"action": "update", "key": "a"}), "needs a 'value'"),
        (
            update("cm-app", {"action": "update", "key": "a", "format": "toml", "entries": {}}),
            "unsupported format",
        ),
        ({"apiVersion": "v1", "kind": "Secret", "metadata": {}}, "metadata.name"),
    ],
)
def test_malformed_changes_name_their_release(document, message) -> None:
    with pytest.raises(ConsolidationDefinitionError, match=f"H001/x.yaml: .*{message}"):
        consolidate([document])


def test_natural_order() -> None:
    names = ["H10", "H9", "H101", "h2", "H010a"]

    assert sorted(names, key=natural_key) == ["h2", "H9", "H10", "H010a", "H101"]


# ----------------------------------------------------------------------
# Plugin
# ----------------------------------------------------------------------


def _yaml(*documents: Dict[str, Any]) -> str:
    return yaml.safe_dump_all(list(documents), sort_keys=False)


def _zip(path: Path, files: Dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _folder(path: Path, files: Dict[str, str]) -> Path:
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return path


class TestPlugin:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.releases = tmp_path / "releases"
        self.releases.mkdir()
        executor = LinuxExecutor()
        self.context = Mock()
        self.context.outputs = {}
        self.context.artifacts = {}
        self.context.activity.return_value = nullcontext()
        self.context.workspace = tmp_path / "workspace"
        self.context.filesystem = executor
        self.context.archive = executor

        # H9 (folder, standard), H10 (ZIP, App-Published), H101 (ZIP, standard).
        _folder(
            self.releases / "H9",
            {
                "App/openshift/yamls/cm.yaml": _yaml(
                    update("cm-app", {"action": "update", "key": "db.url", "value": "A"}),
                    {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "d"}},
                ),
            },
        )
        _zip(
            self.releases / "H10.zip",
            {
                "App-Published/App/yamls/sub/cm.yml": _yaml(
                    update(
                        "cm-app",
                        {"action": "update", "key": "db.url", "value": "B"},
                        {"action": "add", "key": "feature.x", "value": "on"},
                    ),
                    update(
                        "app-secret",
                        {"action": "update", "key": "password", "value": "s"},
                        kind="Secret",
                    ),
                ),
                "App-Published/scripts/deploy/image_transfer.sh": "docker push x\n",
            },
        )
        _zip(
            self.releases / "H101.zip",
            {
                "H101/App/openshift/yamls/cm.yaml": _yaml(
                    update("cm-app", {"action": "delete", "key": "feature.x"}),
                ),
            },
        )

    def _run(self, **arguments: Any):
        self.context.arguments = PluginArguments(arguments)
        return ConsolidateCmSecretPlugin(self.context).execute()

    def test_comments_in_release_files_reach_the_output_file(self) -> None:
        releases = self.tmp / "commented"
        _folder(
            releases / "H1",
            {"App/openshift/yamls/cm.yaml": _commented("# one", "a: 1", "b: 1")},
        )
        _folder(
            releases / "H2",
            {"App/openshift/yamls/cm.yaml": _commented("# two", "c: 2", "# end")},
        )
        output = self.tmp / "output"

        result = self._run(release_directory=str(releases), output_directory=str(output))

        assert result.success
        assert _apply((output / "configmap-cm-app.yaml").read_text(), "a=0\n") == (
            "# one\na=1\nb=1\n# two\nc=2\n# end\n"
        )

    def test_releases_are_consolidated_in_natural_order(self) -> None:
        result = self._run(release_directory=str(self.releases))

        assert result.success is True and result.changed is True
        output = Path(result.outputs["output_directory"])
        assert output == self.tmp / "workspace" / "consolidated" / "cm_secret"
        assert result.outputs["releases"] == ["H9", "H10", "H101"]
        assert sorted(path.name for path in output.iterdir()) == [
            "configmap-cm-app.yaml",
            "consolidation-report.json",
            "secret-app-secret.yaml",
        ]
        assert list(yaml.safe_load_all((output / "configmap-cm-app.yaml").read_text())) == [
            update(
                "cm-app",
                {"action": "update", "key": "db.url", "value": "B"},
                {"action": "delete", "key": "feature.x"},
            )
        ]

        report = json.loads((output / "consolidation-report.json").read_text())
        [configmap] = [item for item in report["targets"] if item["name"] == "cm-app"]
        assert configmap["releases"] == ["H9", "H10", "H101"]
        assert configmap["keys"] == {"db.url": "H10", "feature.x": "H101"}
        assert configmap["sources"][1] == {"release": "H10", "file": "sub/cm.yml"}
        assert report["ignored_documents"] == 1
        assert result.metadata["artifacts"]["consolidation_report"].endswith(
            "consolidation-report.json"
        )

    def test_an_explicit_list_is_applied_as_given(self) -> None:
        result = self._run(
            releases=[str(self.releases / "H101.zip"), str(self.releases / "H10.zip")],
            output_directory=str(self.tmp / "out"),
        )

        assert result.outputs["releases"] == ["H101", "H10"]
        # H10 comes last here, so feature.x is added back.
        [document] = yaml.safe_load_all((self.tmp / "out" / "configmap-cm-app.yaml").read_text())
        assert document["operations"] == [
            {"action": "add", "key": "feature.x", "value": "on"},
            {"action": "update", "key": "db.url", "value": "B"},
        ]

    def test_a_release_without_yamls_is_a_warning(self) -> None:
        _folder(self.releases / "H11", {"DBScripts/a.sql": "select 1;"})

        result = self._run(release_directory=str(self.releases))

        assert result.success is True
        assert result.warnings == ["Release 'H11' has no App/openshift/yamls or App/yamls folder."]

    def test_a_non_empty_output_folder_needs_overwrite(self) -> None:
        output = _folder(self.tmp / "out", {"configmap-stale.yaml": "x: 1\n"})

        refused = self._run(release_directory=str(self.releases), output_directory=str(output))
        assert refused.success is False and "not empty" in refused.errors[0]

        result = self._run(
            release_directory=str(self.releases), output_directory=str(output), overwrite=True
        )
        assert result.success is True
        assert not (output / "configmap-stale.yaml").exists()

    @pytest.mark.parametrize(
        "arguments, message",
        [
            ({}, "either 'release_directory' or 'releases'"),
            ({"release_directory": "/nope", "releases": ["/a.zip"]}, "either"),
            ({"releases": ["/nope/H1.zip"]}, "Release not found"),
        ],
    )
    def test_bad_arguments_fail_cleanly(self, arguments, message) -> None:
        result = self._run(**arguments)

        assert result.success is False and message in result.errors[0]

    def test_a_malformed_change_fails_with_its_location(self) -> None:
        _folder(
            self.releases / "H11",
            {"App/yamls/bad.yaml": _yaml(update("cm-app", {"action": "rename", "key": "a"}))},
        )

        result = self._run(release_directory=str(self.releases))

        assert result.success is False
        assert result.errors[0].startswith("H11/bad.yaml: unsupported operation")


def test_contract_matches_the_source() -> None:
    declared = contract.declared(contract.read_manifest(PLUGIN_DIRECTORY))

    assert declared is not None
    assert contract.check_source(PLUGIN_DIRECTORY, declared) == []


def test_output_is_valid_cm_secret_update_input() -> None:
    """Every consolidated document is accepted by oc.cm_secret_update."""

    from resources.plugins.oc.cm_secret_update.validator import ConfigMapSecretUpdateValidator

    result = consolidate(
        [native("cm-app", {"a": "1"}), native("app-secret", {"p": "eA=="}, kind="Secret")],
        [
            update(
                "cm-app",
                {"action": "update", "key": "a", "value": "2"},
                {"action": "delete", "key": "old"},
                {"action": "update", "key": "p", "format": "properties", "entries": {"x": "1"}},
                {"action": "delete", "key": "y", "format": "yaml", "entries": ["a.b"]},
                {"action": "update", "key": "y", "format": "yaml", "entries": {"a": {"c": 1}}},
            )
        ],
    )

    for target in result.targets:
        for document in yaml.safe_load_all(yaml.safe_dump_all(target.documents())):
            ConfigMapSecretUpdateValidator.parse(document)


# ----------------------------------------------------------------------
# Comments
# ----------------------------------------------------------------------


def _commented(*lines: str) -> str:
    entries = "".join(f"      {line}\n" for line in lines)
    return (
        "apiVersion: entropy/v1\n"
        "kind: ConfigMapSecretUpdate\n"
        "target:\n  kind: ConfigMap\n  name: cm-app\n"
        "operations:\n"
        "  - action: add\n"
        "    format: properties\n"
        "    key: app.properties\n"
        f"    entries:\n{entries}"
    )


def _consolidate_text(*releases: str) -> str:
    """Consolidate YAML texts the way the plugin does, returning the output YAML."""

    filesystem = LinuxExecutor()
    consolidator = Consolidator()
    for number, text in enumerate(releases, start=1):
        for document in filesystem.load_yaml_documents(text):
            consolidator.add(document, Source(release=f"H{number:03d}", file="x.yaml"))
    [target] = consolidator.targets
    return filesystem.serialize_yaml_documents(target.documents())


def _apply(output: str, properties: str) -> str:
    """Apply consolidated YAML with oc.cm_secret_update's real properties updater."""

    updater = _properties_updater()
    filesystem = LinuxExecutor()
    [document] = filesystem.load_yaml_documents(output)
    content = properties
    for operation in document["operations"]:
        if operation["action"] == "delete":
            content, _ = updater.delete(content, operation["entries"])
        else:
            content, _ = updater.update(content, operation["entries"])
    return content


def _properties_updater() -> Any:
    from resources.plugins.oc.cm_secret_update.properties import PropertiesUpdater

    return PropertiesUpdater()


def test_comments_survive_consolidation_and_reach_the_properties() -> None:
    output = _consolidate_text(
        _commented(
            "# first",
            "a: 1 # inline",
            "# second",
            "b: 2",
            "# trailing",
        ),
    )

    assert _apply(output, "a=0\n") == ("# first\n# inline\na=1\n# second\nb=2\n# trailing\n")


def test_consolidated_comments_match_applying_releases_in_sequence() -> None:
    first = _commented("# one", "a: 1", "b: 1")
    second = _commented("# two", "a: 2", "# three", "c: 3")

    sequential = _apply(_consolidate_text(first), "")
    sequential = _apply(_consolidate_text(second), sequential)

    consolidated = _apply(_consolidate_text(first, second), "")

    def parsed(content: str) -> List[str]:
        return sorted(content.splitlines())

    assert parsed(consolidated) == parsed(sequential)
    assert consolidated.index("# one") < consolidated.index("# two") < consolidated.index("a=2")


def test_applying_consolidated_comments_twice_changes_nothing() -> None:
    output = _consolidate_text(_commented("# one", "a: 1", "# two", "b: 2", "# end"))

    once = _apply(output, "x=1\n")

    assert _apply(output, once) == once


def test_later_delete_drops_the_comment_of_a_property() -> None:
    delete = (
        "apiVersion: entropy/v1\n"
        "kind: ConfigMapSecretUpdate\n"
        "target:\n  kind: ConfigMap\n  name: cm-app\n"
        "operations:\n"
        "  - action: delete\n"
        "    format: properties\n"
        "    key: app.properties\n"
        "    entries:\n      - a\n"
    )

    output = _consolidate_text(_commented("# gone", "a: 1", "# stays", "b: 2"), delete)

    assert "# gone" not in output
    assert _apply(output, "a=0\n") == "# stays\nb=2\n"


def test_comments_of_yaml_format_entries_are_not_written() -> None:
    text = _commented("# note", "a: 1").replace("format: properties", "format: yaml")

    assert "# note" not in _consolidate_text(text)


def test_plain_mappings_stay_plain() -> None:
    result = consolidate(
        [
            update(
                "cm-app",
                {"action": "add", "key": "p", "format": "properties", "entries": {"a": "1"}},
            )
        ],
    )

    assert type(operations(result)[0]["entries"]) is dict
