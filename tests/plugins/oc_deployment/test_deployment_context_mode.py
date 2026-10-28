"""
Tests for oc.deployment in deployments mode, fed by release.context_builder.

Covers the release scenarios: image change (Docker build or image transfer),
field changes, both together, and whole-file updates left to another step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import yaml

from lib.executor import LinuxExecutor
from lib.plugins.arguments import PluginArguments
from lib.plugins.contract import check_arguments, declared, read_manifest
from resources.plugins.oc.deployment.plugin import DeploymentPlugin

PLUGIN_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "resources" / "plugins" / "oc" / "deployment"
)

DEPLOYMENT = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "app1"},
    "spec": {
        "template": {
            "spec": {
                "containers": [
                    {
                        "name": "app",
                        "image": "quay.io/sacakti/app1/app-service:0.9.0",
                        "env": [
                            {"name": "MODE", "value": "old"},
                            {"name": "LEGACY", "value": "yes"},
                        ],
                    },
                ],
            },
        },
    },
}

IMAGE_RESOURCE = {
    "name": "app1",
    "kind": "Deployment",
    "action": "UPDATE",
    "file": "app1.yaml",
    "container": "app",
    "current_image": "quay.io/sacakti/app1/app-service:0.9.0",
    "target_image": "quay.io/sacakti/app1/app-service:1.0.0",
}

FIELD_RESOURCE = {
    "name": "app1",
    "kind": "Deployment",
    "action": "UPDATE",
    "file": "app1.yaml",
    "source": "/release/App/openshift/yamls/app1-update.yaml",
    "deployment_update": True,
    "operations": [
        {
            "action": "add",
            "field": "env",
            "container": "app",
            "value": {"name": "NEW", "value": "1"},
        },
        {
            "action": "update",
            "field": "env",
            "container": "app",
            "value": {"name": "MODE", "value": "new"},
        },
        {"action": "delete", "field": "env", "container": "app", "value": {"name": "LEGACY"}},
    ],
}


def _repository(tmp_path: Path) -> Path:
    (tmp_path / "app1.yaml").write_text(yaml.safe_dump(DEPLOYMENT, sort_keys=False))
    return tmp_path


def _run(arguments: dict[str, Any]) -> tuple[Any, MagicMock]:
    context = MagicMock()
    context.arguments = PluginArguments(arguments)
    context.filesystem = LinuxExecutor()
    context.outputs = {}
    context.artifacts = {}
    context.message = Mock()
    context.log = Mock()
    return DeploymentPlugin(context).execute(), context


def _container(repository: Path) -> dict[str, Any]:
    document = yaml.safe_load((repository / "app1.yaml").read_text())
    return document["spec"]["template"]["spec"]["containers"][0]


def _env(repository: Path) -> dict[str, Any]:
    return {item["name"]: item.get("value") for item in _container(repository)["env"]}


def test_contract_accepts_workflow_repository_argument():
    contract = declared(read_manifest(PLUGIN_DIRECTORY))

    arguments = check_arguments(
        contract,
        {
            "mode": "deployments",
            "repository": "/yamls/SIT",
            "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}",
        },
    )

    assert arguments["mode"] == "deployments"
    assert arguments["repository"] == "/yamls/SIT"


def test_folder_only_arguments_are_not_prompted():
    contract = declared(read_manifest(PLUGIN_DIRECTORY))
    prompts = {item["name"]: item.get("prompt") for item in contract["arguments"]}

    assert prompts["source"] is False
    assert prompts["target"] is False
    assert prompts["repository"] is False


def test_image_change_updates_container_image(tmp_path):
    repository = _repository(tmp_path)

    result, _ = _run(
        {"mode": "deployments", "deployments": [{**IMAGE_RESOURCE, "repository": str(repository)}]},
    )

    assert result.success, result.errors
    assert _container(repository)["image"] == "quay.io/sacakti/app1/app-service:1.0.0"
    assert result.outputs["resources_succeeded"] == 1


def test_field_changes_add_update_and_delete_env(tmp_path):
    repository = _repository(tmp_path)

    result, _ = _run(
        {"mode": "deployments", "deployments": [{**FIELD_RESOURCE, "repository": str(repository)}]},
    )

    assert result.success, result.errors
    assert _env(repository) == {"MODE": "new", "NEW": "1"}
    assert _container(repository)["image"] == "quay.io/sacakti/app1/app-service:0.9.0"


def test_image_and_field_changes_for_same_deployment(tmp_path):
    repository = _repository(tmp_path)

    result, _ = _run(
        {
            "mode": "deployments",
            "deployments": [
                {**FIELD_RESOURCE, "repository": str(repository)},
                {**IMAGE_RESOURCE, "repository": str(repository), "image_transfer": True},
            ],
        },
    )

    assert result.success, result.errors
    assert _env(repository) == {"MODE": "new", "NEW": "1"}
    assert _container(repository)["image"] == "quay.io/sacakti/app1/app-service:1.0.0"
    assert result.outputs["resources_succeeded"] == 2


def test_repository_argument_is_used_when_resource_has_none(tmp_path):
    repository = _repository(tmp_path)

    result, _ = _run(
        {"mode": "deployments", "repository": str(repository), "deployments": [IMAGE_RESOURCE]},
    )

    assert result.success, result.errors
    assert _container(repository)["image"] == "quay.io/sacakti/app1/app-service:1.0.0"


def test_whole_file_update_is_skipped_not_failed(tmp_path):
    repository = _repository(tmp_path)
    whole_file = {
        "name": "app1",
        "kind": "Deployment",
        "action": "UPDATE",
        "source": "/release/App/openshift/yamls/app1.yaml",
        "repository": str(repository / "app1.yaml"),
    }

    result, context = _run({"mode": "deployments", "deployments": [whole_file]})

    assert result.success, result.errors
    assert result.outputs["resources_processed"] == 0
    context.message.warning.assert_called_once()
