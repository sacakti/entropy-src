"""
Tests for release.context_builder reading scripts/deploy/image_transfer.sh
into Deployment image updates.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from lib.executor import LinuxExecutor
from resources.plugins.release.context_builder.analyzer import ReleaseAnalyzer

SCRIPT = """#/bin/bash
user=$1
password=$2

docker login azurerepo.io/sacakti $user $password
docker pull azurerepo.io/sacakti/app1/app-service:1.0.0
docker pull azurerepo.io/sacakti/app2/app-service:1.2.0
docker tag azurerepo.io/sacakti/app1/app-service:1.0.0 quay.io/sacakti/app1/app-service:1.0.0
docker push quay.io/sacakti/app1/app-service:1.0.0
docker push quay.io/sacakti/app2/app-service:1.2.0
docker push quay.io/sacakti/app2/app-service:1.2.0
# docker push quay.io/sacakti/app9/app-service:9.9.9
docker push quay.io/sacakti/app3/app-service:$TAG
"""

INDEX = {
    "deployments": {
        "deployments/app1.yaml": {
            "deployment": "app1",
            "containers": {"app": {"image": "quay.io/sacakti/app1/app-service:0.9.0"}},
        },
        "deployments/app2.yaml": {
            "deployment": "app2",
            "containers": {"web": {"image": "mirror.local:5000/sacakti/app2/app-service:1.1.0"}},
        },
    },
}


def _analyzer() -> ReleaseAnalyzer:
    return ReleaseAnalyzer(
        filesystem=LinuxExecutor(),
        archive=Mock(),
        message=Mock(),
        log=Mock(),
        activity=Mock(),
    )


def _script(tmp_path: Path) -> Path:
    script = tmp_path / "scripts" / "deploy" / "image_transfer.sh"
    script.parent.mkdir(parents=True)
    script.write_text(SCRIPT)
    return script


def test_reads_unique_pushed_images_only(tmp_path):
    images = _analyzer()._analyse_image_transfer(_script(tmp_path))

    assert images == [
        "quay.io/sacakti/app1/app-service:1.0.0",
        "quay.io/sacakti/app2/app-service:1.2.0",
    ]


def test_missing_script_yields_no_images(tmp_path):
    assert _analyzer()._analyse_image_transfer(tmp_path / "image_transfer.sh") == []


def test_transferred_images_update_matching_deployments(tmp_path):
    analyzer = _analyzer()

    result = analyzer._build_transfer_deployment_context(
        images=analyzer._analyse_image_transfer(_script(tmp_path)),
        yaml_repository=Path("/yamls/SIT"),
        index=INDEX,
        existing_resources=analyzer._empty_resources(),
    )

    resources = {item["name"]: item for item in result["resources"]["deployments"]}

    assert result["required"] is True
    assert resources["app1"]["target_image"] == "quay.io/sacakti/app1/app-service:1.0.0"
    assert resources["app1"]["file"] == "deployments/app1.yaml"
    assert resources["app1"]["repository"] == "/yamls/SIT"
    # The Deployment keeps its own registry; only the tag changes.
    assert resources["app2"]["container"] == "web"
    assert resources["app2"]["target_image"] == "mirror.local:5000/sacakti/app2/app-service:1.2.0"
    assert result["operations"]["apply"] == [
        "/yamls/SIT/deployments/app1.yaml",
        "/yamls/SIT/deployments/app2.yaml",
    ]


def test_docker_build_image_update_takes_precedence(tmp_path):
    analyzer = _analyzer()
    existing = analyzer._empty_resources()
    existing["deployments"].append(
        {
            "name": "app1",
            "container": "app",
            "action": "UPDATE",
            "target_image": "quay.io/sacakti/app1/app-service:2.0.0",
        },
    )

    result = analyzer._build_transfer_deployment_context(
        images=analyzer._analyse_image_transfer(_script(tmp_path)),
        yaml_repository=Path("/yamls/SIT"),
        index=INDEX,
        existing_resources=existing,
    )

    assert [item["name"] for item in result["resources"]["deployments"]] == ["app2"]


def test_field_update_resource_does_not_block_image_update(tmp_path):
    analyzer = _analyzer()
    existing = analyzer._empty_resources()
    existing["deployments"].append(
        {"name": "app1", "action": "UPDATE", "file": "deployments/app1.yaml", "operations": [{}]},
    )

    result = analyzer._build_transfer_deployment_context(
        images=analyzer._analyse_image_transfer(_script(tmp_path)),
        yaml_repository=Path("/yamls/SIT"),
        index=INDEX,
        existing_resources=existing,
    )

    assert sorted(item["name"] for item in result["resources"]["deployments"]) == ["app1", "app2"]
