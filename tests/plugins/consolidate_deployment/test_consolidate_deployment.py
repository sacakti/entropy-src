"""
Tests for consolidate.deployment: net-operation rules, equivalence with applying
the releases one by one through the real oc.deployment engine, and the plugin
over real release packages.
"""

from __future__ import annotations

import random
import zipfile
from contextlib import nullcontext
from copy import deepcopy
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import Mock

import pytest
import yaml

from lib.executor import LinuxExecutor
from lib.plugins import contract
from lib.plugins.arguments import PluginArguments
from resources.plugins.consolidate.deployment.consolidator import Consolidator, Source
from resources.plugins.consolidate.deployment.exceptions import ConsolidationDefinitionError
from resources.plugins.consolidate.deployment.plugin import ConsolidateDeploymentPlugin
from resources.plugins.oc.deployment.engine import DeploymentUpdateEngine
from resources.plugins.oc.deployment.loader import DeploymentUpdateLoader
from resources.plugins.oc.deployment.validator import DeploymentUpdateValidator

PLUGIN_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "resources" / "plugins" / "consolidate" / "deployment"
)


def update(*operations: Dict[str, Any], name: str = "app-1") -> Dict[str, Any]:
    return {
        "apiVersion": "entropy/v1",
        "kind": "DeploymentUpdate",
        "target": {"kind": "Deployment", "name": name},
        "operations": list(operations),
    }


def env(action: str, value: str = "x", name: str = "MODE") -> Dict[str, Any]:
    return {
        "action": action,
        "field": "env",
        "container": "app",
        "value": {"name": name, "value": value},
    }


def image(tag: str, action: str = "update") -> Dict[str, Any]:
    return {"action": action, "field": "image", "container": "app", "value": f"repo/app:{tag}"}


def native(name: str = "app-1", image_name: str = "repo/app:1") -> Dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {"spec": {"containers": [{"name": "app", "image": image_name}]}},
        },
    }


def consolidate(*releases: List[Dict[str, Any]]) -> Consolidator:
    consolidator = Consolidator()
    for number, documents in enumerate(releases, start=1):
        for document in documents:
            consolidator.add(document, Source(release=f"H{number:03d}", file="x.yaml"))
    return consolidator


def operations(consolidator: Consolidator, name: str = "app-1") -> List[Dict[str, Any]]:
    [target] = [item for item in consolidator.targets if item.name == name]
    document = target.document()
    return document["operations"] if document else []


# ----------------------------------------------------------------------
# Net operations
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("earlier", "later", "expected"),
    [
        ("add", "update", "add"),
        ("update", "update", "update"),
        ("update", "delete", "delete"),
        ("delete", "add", "update"),
    ],
)
def test_two_operations_reduce_to_one(earlier: str, later: str, expected: str) -> None:
    result = operations(consolidate([update(env(earlier, "1"))], [update(env(later, "2"))]))

    assert result == [env(expected, "2")]


def test_add_then_delete_leaves_nothing_and_is_reported() -> None:
    result = consolidate([update(env("add"))], [update(env("delete"))])

    [target] = result.targets

    assert target.document() is None
    assert target.cancelled() == ["env/app/MODE"]


def test_add_after_add_and_delete_is_an_add() -> None:
    result = operations(
        consolidate([update(env("add"))], [update(env("delete"))], [update(env("add", "2"))])
    )

    assert result == [env("add", "2")]


@pytest.mark.parametrize(
    ("earlier", "later", "message"),
    [
        ("add", "add", "already exists"),
        ("update", "add", "already exists"),
        ("delete", "update", "was deleted"),
        ("delete", "delete", "was deleted"),
    ],
)
def test_impossible_sequences_fail_naming_both_releases(
    earlier: str, later: str, message: str
) -> None:
    with pytest.raises(ConsolidationDefinitionError) as error:
        consolidate([update(env(earlier))], [update(env(later))])

    assert str(error.value).startswith(f"H002/x.yaml: cannot {later} env/app/MODE")
    assert message in str(error.value) and "H001" in str(error.value)


def test_latest_image_wins_whatever_the_action() -> None:
    result = operations(
        consolidate([update(image("1"))], [update(image("2", "add"))], [update(image("3"))])
    )

    assert result == [image("3")]


def test_items_are_kept_apart() -> None:
    mount = {
        "action": "add",
        "field": "mounts",
        "container": "app",
        "value": {"name": "MODE", "mountPath": "/m"},
    }
    other_container = {**env("add"), "container": "sidecar"}
    volume = {"action": "add", "field": "mountvolume", "value": {"name": "MODE", "emptyDir": {}}}

    result = consolidate(
        [update(env("add"), mount, other_container, volume, image("1"))],
        [update(env("update", "2"), name="app-2")],
    )

    assert len(operations(result)) == 5
    assert operations(result, "app-2") == [env("update", "2")]
    assert set(result.targets[0].keys()) == {
        "env/app/MODE",
        "mounts/app/MODE",
        "env/sidecar/MODE",
        "mountvolume/MODE",
        "image/app",
    }


def test_other_resources_are_ignored() -> None:
    result = consolidate(
        [
            {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "c"}},
            {"apiVersion": "entropy/v1", "kind": "ConfigMapSecretUpdate"},
            "text",
        ]
    )

    assert result.targets == [] and result.ignored == 3


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (update({"action": "rename", "field": "env"}), "unsupported operation"),
        (update({"action": "add", "field": "replicas"}), "unsupported Deployment field"),
        (update({"action": "add", "field": "env", "value": {"name": "A"}}), "'container'"),
        (update({"action": "add", "field": "env", "container": "a"}), "mapping 'value'"),
        (update({"action": "add", "field": "env", "container": "a", "value": {"x": 1}}), "name"),
        (update({"action": "add", "field": "image", "container": "a", "value": 5}), "string"),
        (update(image("1", "delete")), "not supported"),
        (update({"action": "add", "field": "mountvolume", "container": "a"}), "'container'"),
        ({**update(env("add")), "target": "app"}, "'target'"),
        ({**update(env("add")), "target": {"kind": "Pod", "name": "p"}}, "target kind"),
        ({**update(env("add")), "operations": []}, "'operations'"),
        ({**native(), "metadata": {}}, "metadata.name"),
    ],
)
def test_malformed_changes_name_their_release(document: Dict[str, Any], message: str) -> None:
    with pytest.raises(ConsolidationDefinitionError) as error:
        consolidate([document])

    assert str(error.value).startswith("H001/x.yaml") and message in str(error.value)


def test_a_field_the_validator_accepts_is_also_accepted_here() -> None:
    """The output of the plugin is always valid oc.deployment input."""

    document = update(
        image("1"),
        env("add"),
        {"action": "add", "field": "mounts", "container": "app", "value": {"name": "m"}},
        {"action": "delete", "field": "mountvolume", "value": {"name": "v"}},
    )

    [target] = consolidate([document]).targets

    DeploymentUpdateValidator.parse(target.document())


# ----------------------------------------------------------------------
# Same result as applying the releases one by one
# ----------------------------------------------------------------------


# Each item either exists or not in the Deployment the releases are applied to.
STARTS = list(product((False, True), repeat=6))


def _deployment(start: Tuple[bool, ...]) -> Dict[str, Any]:
    document = native()
    spec = document["spec"]["template"]["spec"]
    container = spec["containers"][0]
    env_items = [{"name": f"E{i}", "value": "start"} for i in range(2) if start[i]]
    mount_items = [{"name": f"M{i}", "mountPath": "/start"} for i in range(2) if start[2 + i]]
    volume_items = [{"name": f"V{i}", "emptyDir": {}} for i in range(2) if start[4 + i]]
    if env_items:
        container["env"] = env_items
    if mount_items:
        container["volumeMounts"] = mount_items
    if volume_items:
        spec["volumes"] = volume_items
    return document


def _random_operation(rng: random.Random) -> Dict[str, Any]:
    field_name = rng.choice(["env", "mounts", "mountvolume", "image"])
    action = rng.choice(["add", "update", "delete"])
    stamp = str(rng.randint(1, 9))
    if field_name == "image":
        return image(stamp, rng.choice(["add", "update"]))
    if field_name == "env":
        value = {"name": rng.choice(["E0", "E1"]), "value": stamp}
    elif field_name == "mounts":
        value = {"name": rng.choice(["M0", "M1"]), "mountPath": f"/{stamp}"}
    else:
        value = {"name": rng.choice(["V0", "V1"]), "configMap": {"name": stamp}}
    operation = {"action": action, "field": field_name, "value": value}
    if field_name != "mountvolume":
        operation["container"] = "app"
    return operation


def _normalized(document: Dict[str, Any]) -> Dict[str, Any]:
    """List order of env, mounts and volumes carries no meaning for the comparison."""

    result = deepcopy(document)
    spec = result["spec"]["template"]["spec"]
    container = spec["containers"][0]
    for holder, name in ((container, "env"), (container, "volumeMounts"), (spec, "volumes")):
        items = sorted(holder.get(name) or [], key=lambda item: item["name"])
        if items:
            holder[name] = items
        else:
            holder.pop(name, None)
    return result


def _apply_in_sequence(start: Dict[str, Any], documents: List[Dict[str, Any]]) -> Optional[Any]:
    engine = DeploymentUpdateEngine()
    current = deepcopy(start)
    for document in documents:
        try:
            engine.apply(current, DeploymentUpdateValidator.parse(document))
        except Exception:  # noqa: BLE001 - any failure means the sequence is invalid here
            return None
    return current


def _sequence(seed: int) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    return [
        update(*[_random_operation(rng) for _ in range(rng.randint(1, 2))])
        for _ in range(rng.randint(2, 4))
    ]


def _compare(documents: List[Dict[str, Any]]) -> int:
    """Check one sequence against every start; returns how many starts it applies to."""

    try:
        [target] = consolidate(*[[document] for document in documents]).targets
    except ConsolidationDefinitionError:
        # Refused: the sequence must then fail for every starting Deployment.
        for values in STARTS:
            assert _apply_in_sequence(_deployment(values), documents) is None
        return 0

    consolidated = target.document()
    compared = 0

    for values in STARTS:
        start = _deployment(values)
        expected = _apply_in_sequence(start, documents)
        actual = _apply_in_sequence(start, [consolidated] if consolidated else [])

        # The consolidated result may not fail where the releases in order succeed.
        if expected is not None:
            assert actual is not None
            assert _normalized(actual) == _normalized(expected)
            compared += 1

    return compared


def test_consolidated_result_matches_applying_in_sequence() -> None:
    compared = sum(_compare(_sequence(seed)) for seed in range(300))

    # Guards the check itself: most sequences must really have been compared.
    assert compared > 1000


# ----------------------------------------------------------------------
# Plugin
# ----------------------------------------------------------------------


def _yaml(*documents: Dict[str, Any]) -> str:
    return yaml.safe_dump_all(list(documents), sort_keys=False)


def _folder(path: Path, files: Dict[str, str]) -> Path:
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return path


def _zip(path: Path, files: Dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


class TestPlugin:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.releases = tmp_path / "releases"
        self.releases.mkdir()
        self.output = tmp_path / "output"
        executor = LinuxExecutor()
        self.executor = executor
        self.context = Mock()
        self.context.outputs = {}
        self.context.artifacts = {}
        self.context.activity.return_value = nullcontext()
        self.context.workspace = tmp_path / "workspace"
        self.context.filesystem = executor
        self.context.archive = executor

    def _run(self, **arguments: Any):
        arguments.setdefault("release_directory", str(self.releases))
        arguments.setdefault("output_directory", str(self.output))
        self.context.arguments = PluginArguments(arguments)
        return ConsolidateDeploymentPlugin(self.context).execute()

    def test_releases_of_every_layout_merge_in_natural_order(self) -> None:
        # H9 (folder, standard), H10 (ZIP, App-Published), H101 (ZIP inside one folder).
        _folder(
            self.releases / "H9",
            {"App/openshift/yamls/d.yaml": _yaml(update(image("9"), env("add", "9")))},
        )
        _zip(
            self.releases / "H10.zip",
            {"App-Published/App/yamls/sub/d.yml": _yaml(update(env("update", "10")))},
        )
        _zip(
            self.releases / "H101.zip",
            {"H101/App/openshift/yamls/d.yaml": _yaml(update(image("101")))},
        )

        result = self._run()

        assert result.success and result.changed
        assert self.context.outputs["releases"] == ["H9", "H10", "H101"]

        [target] = self.context.outputs["targets"]

        assert target["keys"] == {"image/app": "H101", "env/app/MODE": "H10"}

        [definition] = DeploymentUpdateLoader(self.executor).load_directory(self.output)

        assert definition.target.name == "app-1"
        assert [operation.action for operation in definition.operations] == ["update", "add"]
        assert definition.operations[0].value == "repo/app:101"
        assert definition.operations[1].value == {"name": "MODE", "value": "10"}

    def test_cancelled_changes_write_no_file_and_are_reported(self) -> None:
        _folder(self.releases / "H1", {"App/yamls/d.yaml": _yaml(update(env("add")))})
        _folder(self.releases / "H2", {"App/yamls/d.yaml": _yaml(update(env("delete")))})

        result = self._run()

        assert result.success and not result.changed
        assert self.context.outputs["targets"] == []
        assert not (self.output / "deployment-app-1.yaml").exists()

        report = self.executor.read_json(self.output / "consolidation-report.json")

        assert report["cancelled"] == {"app-1": ["env/app/MODE"]}

    def test_complete_resources_stay_out_of_what_oc_deployment_reads(self) -> None:
        _folder(self.releases / "H1", {"App/yamls/d.yaml": _yaml(native(image_name="repo/app:1"))})
        _folder(self.releases / "H2", {"App/yamls/d.yaml": _yaml(native(image_name="repo/app:2"))})
        _folder(self.releases / "H3", {"App/yamls/d.yaml": _yaml(update(image("3")))})

        result = self._run()

        assert result.success

        kept = self.executor.read_yaml(self.output / "native" / "deployment-app-1.yaml")

        assert kept["spec"]["template"]["spec"]["containers"][0]["image"] == "repo/app:2"
        assert len(DeploymentUpdateLoader(self.executor).load_directory(self.output)) == 1
        assert any("only the one of H2 is kept" in warning for warning in result.warnings)
        assert any("does not create" in warning for warning in result.warnings)
        assert any("check that they still fit" in warning for warning in result.warnings)

    def test_a_release_without_yamls_is_a_warning(self) -> None:
        _folder(self.releases / "H1", {"App/yamls/d.yaml": _yaml(update(image("1")))})
        _folder(self.releases / "H2", {"docs/readme.txt": "x"})

        result = self._run()

        assert result.success
        assert any("'H2' has no App/openshift/yamls" in warning for warning in result.warnings)

    def test_an_impossible_sequence_fails_cleanly(self) -> None:
        _folder(self.releases / "H1", {"App/yamls/d.yaml": _yaml(update(env("add")))})
        _folder(self.releases / "H2", {"App/yamls/d.yaml": _yaml(update(env("add")))})

        result = self._run()

        assert result.success is False
        assert result.errors[0]["message"].startswith("H2/d.yaml: cannot add env/app/MODE")

    def test_non_empty_output_needs_overwrite(self) -> None:
        _folder(self.releases / "H1", {"App/yamls/d.yaml": _yaml(update(image("1")))})
        _folder(self.output, {"old.yaml": "stale"})

        assert self._run().success is False

        assert self._run(overwrite=True).success
        assert not (self.output / "old.yaml").exists()


def test_contract_matches_the_source() -> None:
    declared = contract.declared(contract.read_manifest(PLUGIN_DIRECTORY))

    assert declared is not None
    assert contract.check_source(PLUGIN_DIRECTORY, declared) == []
