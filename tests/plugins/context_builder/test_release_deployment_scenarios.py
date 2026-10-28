"""
End-to-end release scenarios: release.context_builder output fed into
oc.deployment (deployments mode).

[1] App/services/<image> build + App/openshift/yamls DeploymentUpdate
[2] App-Published package: App/yamls DeploymentUpdate + scripts/deploy/image_transfer.sh
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import yaml

from lib.executor import LinuxExecutor
from lib.plugins.arguments import PluginArguments
from resources.plugins.oc.deployment.plugin import DeploymentPlugin
from resources.plugins.release.context_builder.analyzer import ReleaseAnalyzer

STRUCTURE = (
    Path(__file__).resolve().parents[3]
    / "resources"
    / "plugins"
    / "release"
    / "context_builder"
    / "structure.yaml"
)

DEPLOYMENT_UPDATE = """apiVersion: entropy/v1
kind: DeploymentUpdate
target:
  kind: Deployment
  name: app-1
operations:
  - action: add
    field: env
    container: app
    value:
      name: APP_MODE
      value: production
  - action: update
    field: env
    container: app
    value:
      name: LOG_LEVEL
      value: debug
"""

TRANSFER_SCRIPT = """#/bin/bash
docker login azurerepo.io/sacakti $1 $2
docker pull azurerepo.io/sacakti/app-1:2.0.0
docker tag azurerepo.io/sacakti/app-1:2.0.0 quay.io/sacakti/app-1:2.0.0
docker push quay.io/sacakti/app-1:2.0.0
"""


def _yaml_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "yamls"
    (repository / "deployments").mkdir(parents=True)
    (repository / ".entropy").mkdir()
    (repository / "deployments" / "app-1.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "app-1"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "app",
                                    "image": "quay.io/sacakti/app-1:1.0.0",
                                    "env": [{"name": "LOG_LEVEL", "value": "info"}],
                                },
                            ],
                        },
                    },
                },
            },
            sort_keys=False,
        ),
    )
    (repository / ".entropy" / "resource_index.json").write_text(
        json.dumps(
            {
                "resources": {"Deployment": {"app-1": {"file": "deployments/app-1.yaml"}}},
                "deployments": {
                    "deployments/app-1.yaml": {
                        "deployment": "app-1",
                        "containers": {"app": {"image": "quay.io/sacakti/app-1:1.0.0"}},
                    },
                },
            },
        ),
    )
    return repository


def _docker_repository(tmp_path: Path) -> Path:
    image = tmp_path / "docker" / "app-1" / "image"
    image.mkdir(parents=True)
    (image / "app1.war").write_text("old build")
    return tmp_path / "docker"


def _release(tmp_path: Path, files: dict[str, str]) -> Path:
    release = tmp_path / "release.zip"
    with zipfile.ZipFile(release, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return release


def _analyse(tmp_path: Path, release: Path) -> tuple[dict[str, Any], Path]:
    executor = LinuxExecutor()
    yaml_repository = _yaml_repository(tmp_path)
    context = ReleaseAnalyzer(
        filesystem=executor,
        archive=executor,
        message=Mock(),
        log=Mock(),
        activity=MagicMock(),
    ).analyze(
        release=release,
        docker_repository=_docker_repository(tmp_path),
        yaml_repository=yaml_repository,
        image_tag="2.0.0",
        structure=STRUCTURE,
    )
    return context, yaml_repository


def _deploy(deployments: list[dict[str, Any]]) -> Any:
    context = MagicMock()
    context.arguments = PluginArguments({"mode": "deployments", "deployments": deployments})
    context.filesystem = LinuxExecutor()
    context.outputs = {}
    context.artifacts = {}
    return DeploymentPlugin(context).execute()


def _container(yaml_repository: Path) -> dict[str, Any]:
    document = yaml.safe_load((yaml_repository / "deployments" / "app-1.yaml").read_text())
    return document["spec"]["template"]["spec"]["containers"][0]


def _assert_image_and_fields_updated(yaml_repository: Path) -> None:
    container = _container(yaml_repository)
    assert container["image"] == "quay.io/sacakti/app-1:2.0.0"
    assert {item["name"]: item["value"] for item in container["env"]} == {
        "LOG_LEVEL": "debug",
        "APP_MODE": "production",
    }


def test_docker_build_with_deployment_update(tmp_path):
    release = _release(
        tmp_path,
        {
            "R1/App/services/app-1/image/app1.war": "new build",
            "R1/App/openshift/yamls/deployment.yaml": DEPLOYMENT_UPDATE,
        },
    )

    context, yaml_repository = _analyse(tmp_path, release)
    deployments = context["deployment"]["resources"]["deployments"]

    assert "app-1" in context["images"]
    assert len(deployments) == 2

    result = _deploy(deployments)

    assert result.success, result.errors
    _assert_image_and_fields_updated(yaml_repository)


def test_published_package_with_image_transfer_and_deployment_update(tmp_path):
    release = _release(
        tmp_path,
        {
            "App-Published/App/yamls/deployment.yaml": DEPLOYMENT_UPDATE,
            "App-Published/scripts/deploy/image_transfer.sh": TRANSFER_SCRIPT,
        },
    )

    context, yaml_repository = _analyse(tmp_path, release)
    deployments = context["deployment"]["resources"]["deployments"]

    assert context["images"] == {}
    assert len(deployments) == 2
    assert context["deployment"]["required"] is True

    result = _deploy(deployments)

    assert result.success, result.errors
    _assert_image_and_fields_updated(yaml_repository)


def test_scripts_only_package_with_image_transfer(tmp_path):
    release = _release(
        tmp_path,
        {"H001/scripts/deploy/image_transfer.sh": TRANSFER_SCRIPT},
    )

    context, yaml_repository = _analyse(tmp_path, release)
    deployments = context["deployment"]["resources"]["deployments"]

    assert [item.get("image_transfer") for item in deployments] == [True]

    result = _deploy(deployments)

    assert result.success, result.errors
    container = _container(yaml_repository)
    assert container["image"] == "quay.io/sacakti/app-1:2.0.0"
    assert {item["name"]: item["value"] for item in container["env"]} == {"LOG_LEVEL": "info"}
