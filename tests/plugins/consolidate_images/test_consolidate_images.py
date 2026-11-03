"""
Tests for consolidate.images over real release packages, and for the consolidation
workflow: real consolidate and oc plugins; Docker and sqlplus are never run.
"""

from __future__ import annotations

import json
import re
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
from resources.plugins.consolidate.cm_secret.plugin import ConsolidateCmSecretPlugin
from resources.plugins.consolidate.deployment.plugin import ConsolidateDeploymentPlugin
from resources.plugins.consolidate.images.plugin import ConsolidateImagesPlugin
from resources.plugins.consolidate.images.transfer import (
    TransferImage,
    parse_transfer_script,
    render_transfer_script,
)
from resources.plugins.oc.cm_secret_update.plugin import CmSecretUpdatePlugin
from resources.plugins.oc.deployment.plugin import DeploymentPlugin

PLUGINS = Path(__file__).resolve().parents[3] / "resources" / "plugins"
PLUGIN_DIRECTORY = PLUGINS / "consolidate" / "images"

TRANSFER = """#!/bin/bash
user=$1
password=$2
docker login azurerepo.io/acme $user $password
docker pull azurerepo.io/acme/{name}:{tag}
docker login quay.io/acme $user $password
docker tag azurerepo.io/acme/{name}:{tag} quay.io/acme/{name}:{tag}
docker push quay.io/acme/{name}:{tag}
"""

PUSH_A = {"scripts/deploy/image_transfer.sh": "docker push quay.io/a:9\n"}


def _folder(path: Path, files: Dict[str, str]) -> Path:
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return path


def _zip(path: Path, files: Dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _service(name: str, war: str = "app.war") -> Dict[str, str]:
    return {
        f"App/services/{name}/image/Dockerfile": "FROM scratch\n",
        f"App/services/{name}/image/{war}": f"{war}\n",
    }


def _context(tmp_path: Path, arguments: Dict[str, Any]) -> Mock:
    executor = LinuxExecutor()
    context = Mock()
    context.outputs = {}
    context.artifacts = {}
    context.activity.return_value = nullcontext()
    context.workspace = tmp_path / "workspace"
    context.filesystem = executor
    context.archive = executor
    context.arguments = PluginArguments(arguments)
    return context


class TestTransferScript:
    def test_reads_what_each_push_needs(self) -> None:
        warnings: List[str] = []

        images = parse_transfer_script(TRANSFER.format(name="a", tag="1"), warnings, "H1")

        assert images == [
            TransferImage("quay.io/acme/a:1", "azurerepo.io/acme/a:1", True),
        ]
        assert warnings == []

    @pytest.mark.parametrize(
        "line",
        [
            "sudo docker push quay.io/a:1",
            "docker image push quay.io/a:1",
            "docker push --platform linux/amd64 quay.io/a:1",
            "cd /tmp && docker push quay.io/a:1 # done",
            "docker \\\n  push quay.io/a:1",
        ],
    )
    def test_finds_pushes_however_they_are_written(self, line: str) -> None:
        images = parse_transfer_script(line, [], "H1")

        assert [item.image for item in images] == ["quay.io/a:1"]

    @pytest.mark.parametrize(
        ("line", "reason"),
        [
            ("docker push quay.io/a:$TAG", "shell variable"),
            ("docker push quay.io/a", "no tag"),
            ("docker tag x:$V quay.io/a:1\ndocker push quay.io/a:1", "shell variable"),
        ],
    )
    def test_reports_pushes_it_cannot_use(self, line: str, reason: str) -> None:
        warnings: List[str] = []

        assert parse_transfer_script(line, warnings, "H1") == []
        assert reason in warnings[0] and warnings[0].startswith("H1")

    def test_a_comment_is_not_a_push(self) -> None:
        assert parse_transfer_script("# docker push quay.io/a:1", [], "H1") == []

    def test_script_logs_in_without_credentials_then_pulls_tags_and_pushes(self) -> None:
        script = render_transfer_script(
            [TransferImage("quay.io/acme/a:1", "azurerepo.io/acme/a:1", True)]
        )

        commands = [line for line in script.splitlines() if line.startswith("docker")]
        assert commands == [
            "docker login azurerepo.io",
            "docker login quay.io",
            "docker pull azurerepo.io/acme/a:1",
            "docker tag azurerepo.io/acme/a:1 quay.io/acme/a:1",
            "docker push quay.io/acme/a:1",
        ]
        assert script.index("set -e") < script.index("docker login")

    def test_script_without_images_runs_no_docker_command(self) -> None:
        script = render_transfer_script([])

        assert not re.search(r"^docker", script, re.MULTILINE)


class TestPlugin:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.releases = tmp_path / "releases"
        self.releases.mkdir()
        self.output = tmp_path / "output"

    def _run(self, **arguments: Any):
        arguments.setdefault("release_directory", str(self.releases))
        arguments.setdefault("output_directory", str(self.output))
        arguments.setdefault("image_tag", "2.0")
        self.context = _context(self.tmp, arguments)
        return ConsolidateImagesPlugin(self.context).execute()

    @property
    def outputs(self) -> Dict[str, Any]:
        return self.context.outputs

    def _index(self, **containers: str) -> Path:
        repository = self.tmp / "yamls"
        index = {
            "deployments": {
                f"deployments/{name}.yaml": {
                    "deployment": name,
                    "containers": {"app": {"image": image}},
                }
                for name, image in containers.items()
            }
        }
        _folder(repository, {".entropy/resource_index.json": json.dumps(index)})
        return repository

    def test_releases_with_any_mix_of_content(self) -> None:
        _zip(
            self.releases / "H001.zip",
            {"scripts/deploy/image_transfer.sh": TRANSFER.format(name="a", tag="1")},
        )
        _zip(self.releases / "H002.zip", _service("app-1"))
        _zip(
            self.releases / "H003.zip",
            {"App-Published/scripts/deploy/image_transfer.sh": TRANSFER.format(name="b", tag="3")},
        )
        _zip(self.releases / "H004.zip", {"DBScripts/App1/a.sql": "select 1 from dual;\n"})

        result = self._run()

        assert result.success and result.changed
        assert list(self.outputs["images"]) == ["app-1"]
        assert self.outputs["transfers"] == ["quay.io/acme/a:1", "quay.io/acme/b:3"]

    def test_image_is_described_for_docker_build(self) -> None:
        _zip(self.releases / "H1.zip", _service("app-1"))

        assert self._run().success

        context = self.output / "services" / "app-1"
        assert self.outputs["images"]["app-1"] == {
            "dockerfile": str(context / "image" / "Dockerfile"),
            "context": str(context),
            "image_name": "app-1",
            "image_tag": "2.0",
        }
        assert (context / "image" / "app.war").read_text() == "app.war\n"

    def test_the_latest_release_replaces_an_image_and_names_what_is_dropped(self) -> None:
        # Natural order: H9 before H10.
        _folder(self.releases / "H9", _service("app-1", "old.war"))
        _folder(self.releases / "H10", _service("app-1", "new.war"))

        result = self._run()

        image = self.output / "services" / "app-1" / "image"
        assert sorted(path.name for path in image.iterdir()) == ["Dockerfile", "new.war"]
        assert any("H10 replaces" in item and "old.war" in item for item in result.warnings)

    def test_an_explicit_order_decides_the_latest(self) -> None:
        first = _folder(self.tmp / "other" / "H2", _service("app-1", "two.war"))
        second = _folder(self.tmp / "other" / "H1", _service("app-1", "one.war"))

        assert self._run(release_directory=None, releases=[str(first), str(second)]).success

        assert (self.output / "services" / "app-1" / "image" / "one.war").exists()

    def test_the_latest_push_to_a_repository_wins(self) -> None:
        _folder(
            self.releases / "H1",
            {"scripts/deploy/image_transfer.sh": TRANSFER.format(name="a", tag="1")},
        )
        _folder(
            self.releases / "H2",
            {"scripts/deploy/image_transfer.sh": TRANSFER.format(name="a", tag="2")},
        )

        assert self._run().success

        assert self.outputs["transfers"] == ["quay.io/acme/a:2"]
        script = Path(self.outputs["transfer_script"]).read_text()
        assert "a:2" in script and "a:1" not in script

    def test_an_image_without_a_dockerfile_fails_naming_the_release(self) -> None:
        _folder(self.releases / "H1", {"App/services/app-1/image/app.war": "x"})

        result = self._run()

        assert not result.success
        assert "'H1'" in result.errors[0]["message"]
        assert "'app-1'" in result.errors[0]["message"]

    def test_no_images_succeeds_with_nothing_to_do(self) -> None:
        _folder(self.releases / "H1", {"DBScripts/App1/a.sql": "select 1 from dual;\n"})

        result = self._run(yaml_repository=str(self._index()))

        assert result.success and not result.changed
        assert self.outputs["images"] == {} and self.outputs["deployments"] == []
        assert not re.search(
            r"^docker", Path(self.outputs["transfer_script"]).read_text(), re.MULTILINE
        )

    def test_an_identical_released_image_is_not_built(self) -> None:
        _folder(self.releases / "H1", {**_service("same"), **_service("diff")})
        repository = self.tmp / "docker"
        _folder(
            repository,
            {
                "same/image/Dockerfile": "FROM scratch\n",
                "same/image/app.war": "app.war\n",
                "diff/image/Dockerfile": "FROM scratch\n",
                "diff/image/app.war": "older\n",
            },
        )

        assert self._run(docker_repository=str(repository)).success

        assert list(self.outputs["images"]) == ["diff"]

    def test_a_new_service_is_built(self) -> None:
        _folder(self.releases / "H1", _service("new"))
        (self.tmp / "docker").mkdir()

        assert self._run(docker_repository=str(self.tmp / "docker")).success

        assert list(self.outputs["images"]) == ["new"]

    def test_apply_script_is_reported_as_not_consolidated(self) -> None:
        _folder(self.releases / "H1", {"scripts/deploy/apply_yaml.sh": "oc apply -f x\n"})

        result = self._run()

        assert result.success and "apply_yaml.sh is not consolidated" in result.warnings[0]

    def test_deployment_updates_keep_the_registry_of_the_deployment(self) -> None:
        _folder(self.releases / "H1", _service("app-1"))

        repository = self._index(one="internal:5000/ns/app-1:1.0")

        assert self._run(yaml_repository=str(repository)).success

        assert self.outputs["deployments"] == [
            {
                "name": "one",
                "kind": "Deployment",
                "action": "UPDATE",
                "file": "deployments/one.yaml",
                "repository": str(repository),
                "container": "app",
                "current_image": "internal:5000/ns/app-1:1.0",
                "target_image": "internal:5000/ns/app-1:2.0",
            }
        ]

    def test_transfer_matches_by_path_then_by_a_unique_name(self) -> None:
        _folder(
            self.releases / "H1",
            {
                "scripts/deploy/image_transfer.sh": "docker push quay.io/acme/a:9\n"
                "docker push quay.io/elsewhere/b:9\n"
            },
        )

        result = self._run(
            yaml_repository=str(self._index(one="quay.io/acme/a:1", two="internal/ns/b:1"))
        )

        assert result.success
        assert [(item["name"], item["target_image"]) for item in self.outputs["deployments"]] == [
            ("one", "quay.io/acme/a:9"),
            ("two", "internal/ns/b:9"),
        ]
        assert all(item["image_transfer"] for item in self.outputs["deployments"])
        assert any("by the name 'b' only" in item for item in result.warnings)

    def test_an_ambiguous_name_updates_nothing_and_warns(self) -> None:
        _folder(
            self.releases / "H1",
            {"scripts/deploy/image_transfer.sh": "docker push quay.io/x/b:9\n"},
        )

        result = self._run(yaml_repository=str(self._index(one="n1/b:1", two="n2/b:1")))

        assert result.success and self.outputs["deployments"] == []
        assert any("ambiguous" in item for item in result.warnings)

    @pytest.mark.parametrize(
        ("first", "second", "expected"),
        [
            # A later transfer beats an earlier build, and the other way round.
            (_service("a"), {"scripts/deploy/image_transfer.sh": "docker push quay.io/a:9\n"}, "9"),
            (
                {"scripts/deploy/image_transfer.sh": "docker push quay.io/a:9\n"},
                _service("a"),
                "2.0",
            ),
        ],
    )
    def test_the_latest_release_sets_a_container_image(self, first, second, expected) -> None:
        _folder(self.releases / "H1", first)
        _folder(self.releases / "H2", second)

        assert self._run(yaml_repository=str(self._index(one="quay.io/a:1"))).success

        assert [item["target_image"] for item in self.outputs["deployments"]] == [
            f"quay.io/a:{expected}"
        ]

    def test_within_a_release_the_built_image_wins(self) -> None:
        _folder(
            self.releases / "H1",
            {**_service("a"), "scripts/deploy/image_transfer.sh": "docker push quay.io/a:9\n"},
        )

        assert self._run(yaml_repository=str(self._index(one="quay.io/a:1"))).success

        assert [item["target_image"] for item in self.outputs["deployments"]] == ["quay.io/a:2.0"]

    def test_a_missing_index_fails_before_the_output_is_emptied(self) -> None:
        _folder(self.releases / "H1", _service("a"))
        _folder(self.output, {"keep.txt": "x"})

        result = self._run(yaml_repository=str(self.tmp / "none"), overwrite=True)

        assert not result.success and "oc.sync_yamls" in result.errors[0]["message"]
        assert (self.output / "keep.txt").exists()

    def test_a_non_empty_output_is_refused(self) -> None:
        _folder(self.releases / "H1", _service("a"))
        _folder(self.output, {"keep.txt": "x"})

        assert not self._run().success
        assert self._run(overwrite=True).success

    def test_image_tag_is_required(self) -> None:
        _folder(self.releases / "H1", _service("a"))

        assert not self._run(image_tag="").success


def test_contract_matches_the_source() -> None:
    declared = contract.declared(contract.read_manifest(PLUGIN_DIRECTORY))

    assert declared is not None
    assert contract.check_source(PLUGIN_DIRECTORY, declared) == []


# ----------------------------------------------------------------------
# Applying empty output, and a repository from oc.sync_yamls
# ----------------------------------------------------------------------


def _deployment(name: str, image: str) -> Dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {"containers": [{"name": "app", "image": image, "env": []}]},
            }
        },
    }


def _configmap(name: str, **data: str) -> Dict[str, Any]:
    return {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": name}, "data": data}


@pytest.fixture
def empty_output(tmp_path: Path) -> Path:
    # All a consolidation writes when no release has changes of this kind.
    return _folder(tmp_path / "empty", {"consolidation-report.json": "{}"})


@pytest.mark.parametrize("plugin", [CmSecretUpdatePlugin, DeploymentPlugin])
def test_empty_source_still_fails_by_default(plugin, tmp_path, empty_output) -> None:
    (tmp_path / "target").mkdir()
    arguments = {"mode": "folder", "source": str(empty_output), "target": str(tmp_path / "target")}

    assert not plugin(_context(tmp_path, arguments)).execute().success


@pytest.mark.parametrize("plugin", [CmSecretUpdatePlugin, DeploymentPlugin])
def test_allow_empty_succeeds_without_changes(plugin, tmp_path, empty_output) -> None:
    (tmp_path / "target").mkdir()
    arguments = {
        "mode": "folder",
        "source": str(empty_output),
        "target": str(tmp_path / "target"),
        "allow_empty": True,
    }

    result = plugin(_context(tmp_path, arguments)).execute()

    assert result.success and not result.changed
    assert result.outputs["resources_processed"] == 0
    assert list((tmp_path / "target").iterdir()) == []


@pytest.mark.parametrize("plugin", [CmSecretUpdatePlugin, DeploymentPlugin])
def test_allow_empty_does_not_hide_a_missing_source(plugin, tmp_path) -> None:
    (tmp_path / "target").mkdir()
    arguments = {
        "mode": "folder",
        "source": str(tmp_path / "missing"),
        "target": str(tmp_path / "target"),
        "allow_empty": True,
    }

    assert not plugin(_context(tmp_path, arguments)).execute().success


def _cm_update(name: str, key: str, value: str) -> str:
    return yaml.safe_dump(
        {
            "apiVersion": "entropy/v1",
            "kind": "ConfigMapSecretUpdate",
            "target": {"kind": "ConfigMap", "name": name},
            "operations": [{"action": "update", "key": key, "value": value}],
        }
    )


def test_recursive_finds_targets_in_repository_folders(tmp_path) -> None:
    repository = _folder(
        tmp_path / "yamls",
        {
            "configmaps/cm.yaml": yaml.safe_dump(_configmap("cm", a="1")),
            "deployments/one.yaml": yaml.safe_dump(_deployment("one", "x:1")),
            # Another kind beside a ConfigMap survives the write.
            "configmaps/mixed.yaml": yaml.safe_dump_all(
                [_configmap("other", b="1"), _deployment("two", "x:1")]
            ),
        },
    )
    source = _folder(tmp_path / "source", {"cm.yaml": _cm_update("other", "b", "2")})

    result = CmSecretUpdatePlugin(
        _context(
            tmp_path,
            {"mode": "folder", "source": str(source), "target": str(repository), "recursive": True},
        )
    ).execute()

    assert result.success, result.errors
    documents = list(yaml.safe_load_all((repository / "configmaps/mixed.yaml").read_text()))
    assert documents[0]["data"]["b"] == "2"
    assert documents[1]["kind"] == "Deployment"
    # Nothing was written beside the folders.
    assert sorted(path.name for path in repository.iterdir()) == ["configmaps", "deployments"]


# ----------------------------------------------------------------------
# The workflow
# ----------------------------------------------------------------------


WORKFLOW = json.loads((PLUGIN_DIRECTORY / "workflow.json").read_text())


def _manifest(plugin: str) -> Dict[str, Any]:
    namespace, name = plugin.split(".")
    return json.loads((PLUGINS / namespace / name / "plugin.json").read_text())


def test_workflow_uses_declared_arguments_and_outputs() -> None:
    steps = {step["name"]: step for step in WORKFLOW["steps"]}

    for step in WORKFLOW["steps"]:
        manifest = _manifest(step["plugin"])

        if manifest.get("arguments"):
            declared = {item["name"] for item in manifest["arguments"]}
            assert set(step["arguments"]) <= declared, step["name"]

        for value in step["arguments"].values():
            text = str(value)

            for source, output in re.findall(r"\$\{steps\.(\w+)\.outputs\.(\w+)\}", text):
                outputs = {item["name"] for item in _manifest(steps[source]["plugin"])["outputs"]}
                assert output in outputs, f"{step['name']}: {source}.{output}"
                # Output of an earlier step only.
                assert list(steps).index(source) < list(steps).index(step["name"])

            for variable in re.findall(r"\$\{(\w+)\}", text):
                assert variable in WORKFLOW["variables"], f"{step['name']}: {variable}"


def _arguments(step: str, **values: str) -> Dict[str, Any]:
    arguments = next(item for item in WORKFLOW["steps"] if item["name"] == step)["arguments"]
    resolved = json.dumps(arguments)

    for name, value in values.items():
        resolved = resolved.replace(f'"${{{name}}}"', json.dumps(value))
        resolved = resolved.replace(f"${{{name}}}", str(value))

    return json.loads(resolved)


def test_workflow_applies_releases_with_different_content(tmp_path) -> None:
    """H1 has a ConfigMap change and a transfer; H2 a Deployment change and a service."""

    h1 = _zip(
        tmp_path / "releases" / "H1.zip",
        {
            "App/openshift/yamls/cm.yaml": _cm_update("cm", "a", "2"),
            "scripts/deploy/image_transfer.sh": TRANSFER.format(name="moved", tag="7"),
        },
    )
    h2 = _zip(
        tmp_path / "releases" / "H2.zip",
        {
            **_service("built"),
            "App/openshift/yamls/env.yaml": yaml.safe_dump(
                {
                    "apiVersion": "entropy/v1",
                    "kind": "DeploymentUpdate",
                    "target": {"kind": "Deployment", "name": "built"},
                    "operations": [
                        {
                            "action": "add",
                            "field": "env",
                            "container": "app",
                            "value": {"name": "MODE", "value": "on"},
                        }
                    ],
                }
            ),
        },
    )
    repository = _folder(
        tmp_path / "yamls",
        {
            "configmaps/cm.yaml": yaml.safe_dump(_configmap("cm", a="1")),
            "deployments/built.yaml": yaml.safe_dump(_deployment("built", "quay.io/acme/built:1")),
            "deployments/moved.yaml": yaml.safe_dump(_deployment("moved", "quay.io/acme/moved:1")),
            ".entropy/resource_index.json": json.dumps(
                {
                    "deployments": {
                        "deployments/built.yaml": {
                            "deployment": "built",
                            "containers": {"app": {"image": "quay.io/acme/built:1"}},
                        },
                        "deployments/moved.yaml": {
                            "deployment": "moved",
                            "containers": {"app": {"image": "quay.io/acme/moved:1"}},
                        },
                    }
                }
            ),
        },
    )

    values = {"releases": [str(h1), str(h2)], "yaml_repository": str(repository)}
    outputs: Dict[str, Dict[str, Any]] = {}

    def run(step: str, plugin: Any, **extra: Any) -> None:
        arguments = {**_arguments(step, **values), **extra}
        arguments = {
            key: value
            for key, value in arguments.items()
            if not (isinstance(value, str) and "${" in value)
        }
        context = _context(tmp_path, arguments)
        result = plugin(context).execute()
        assert result.success, (step, result.errors)
        outputs[step] = context.outputs

    run("ConsolidateCmSecret", ConsolidateCmSecretPlugin)
    run("ConsolidateDeployment", ConsolidateDeploymentPlugin)
    run(
        "ConsolidateImages",
        ConsolidateImagesPlugin,
        image_tag="2.0",
        docker_repository=str(tmp_path / "no-docker-repository"),
    )
    run(
        "ApplyCmSecret",
        CmSecretUpdatePlugin,
        source=outputs["ConsolidateCmSecret"]["output_directory"],
    )
    run(
        "ApplyDeployment",
        DeploymentPlugin,
        source=outputs["ConsolidateDeployment"]["output_directory"],
    )
    run(
        "ApplyImages",
        DeploymentPlugin,
        deployments=outputs["ConsolidateImages"]["deployments"],
    )

    assert yaml.safe_load((repository / "configmaps/cm.yaml").read_text())["data"]["a"] == "2"

    def container(name: str) -> Dict[str, Any]:
        document = yaml.safe_load((repository / f"deployments/{name}.yaml").read_text())
        return document["spec"]["template"]["spec"]["containers"][0]

    assert container("built")["image"] == "quay.io/acme/built:2.0"
    assert container("built")["env"] == [{"name": "MODE", "value": "on"}]
    assert container("moved")["image"] == "quay.io/acme/moved:7"
    assert list(outputs["ConsolidateImages"]["images"]) == ["built"]
