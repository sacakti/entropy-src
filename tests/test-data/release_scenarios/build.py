#!/usr/bin/env python3
"""
Build a sandbox for the release.context_builder -> custom.image_transfer ->
oc.deployment scenarios, and the workflow that runs them.

Usage:
    python build.py <sandbox directory>

The sandbox holds release ZIPs, a Docker repository, one YAML repository per
scenario (with .entropy/resource_index.json), and release-scenarios.json.
Nothing outside the sandbox is touched. Docker is never called: image
transfer steps run with skip_docker.
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict

import yaml

MARKER = ".release-scenarios"
IMAGE_TAG = "2.0.0"

# ----------------------------------------------------------------------
# Environment (what the cluster runs before the release)
# ----------------------------------------------------------------------


def deployment(name: str, container: str, image: str, **extra: Any) -> Dict[str, Any]:
    spec: Dict[str, Any] = {"containers": [{"name": container, "image": image, **extra}]}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"template": {"spec": spec}},
    }


ENVIRONMENT = {
    "app-1": deployment(
        "app-1", "app", "quay.io/sacakti/app-1:1.0.0", env=[{"name": "LOG_LEVEL", "value": "info"}]
    ),
    "app1": deployment(
        "app1",
        "app-service",
        "quay.io/sacakti/app1/app-service:1.0.0",
        env=[{"name": "LOG_LEVEL", "value": "info"}],
    ),
    "app-2": deployment("app-2", "web", "quay.io/sacakti/app-2:1.0.0"),
}

# ----------------------------------------------------------------------
# Release content
# ----------------------------------------------------------------------

APP_1_UPDATE = {
    "apiVersion": "entropy/v1",
    "kind": "DeploymentUpdate",
    "target": {"kind": "Deployment", "name": "app-1"},
    "operations": [
        {
            "action": "add",
            "field": "env",
            "container": "app",
            "value": {"name": "APP_MODE", "value": "production"},
        },
        {
            "action": "update",
            "field": "env",
            "container": "app",
            "value": {"name": "LOG_LEVEL", "value": "debug"},
        },
        {
            "action": "add",
            "field": "mountvolume",
            "value": {"name": "app-config", "configMap": {"name": "app-config"}},
        },
        {
            "action": "add",
            "field": "mounts",
            "container": "app",
            "value": {"name": "app-config", "mountPath": "/etc/app"},
        },
    ],
}

APP1_UPDATE = {
    "apiVersion": "entropy/v1",
    "kind": "DeploymentUpdate",
    "target": {"kind": "Deployment", "name": "app1"},
    "operations": [
        {
            "action": "add",
            "field": "env",
            "container": "app-service",
            "value": {"name": "APP_MODE", "value": "published"},
        },
        {
            "action": "delete",
            "field": "env",
            "container": "app-service",
            "value": {"name": "LOG_LEVEL"},
        },
    ],
}


def transfer_script(tag: str) -> str:
    # Positional credentials on purpose: they must be stripped.
    return f"""#/bin/bash
user=$1
password=$2

docker login azurerepo.io/sacakti $user $password
docker pull azurerepo.io/sacakti/app1/app-service:{tag}

docker login quay.io/sacakti -u $user -p $password
docker tag azurerepo.io/sacakti/app1/app-service:{tag} quay.io/sacakti/app1/app-service:{tag}
docker push quay.io/sacakti/app1/app-service:{tag}
"""


def apply_script(prefix: str) -> str:
    # git and oc login credentials on purpose: they must be removed.
    return f"""#!/bin/bash
user=$1
password=$2
oc login -u $user -p $password https://api.example.cluster:6443
git pull
oc apply -f /home/devops/{prefix}scripts/app1/deployment.yaml
"""


def dumps(document: Dict[str, Any]) -> str:
    return yaml.safe_dump(document, sort_keys=False)


DOCKERFILE = "FROM registry.access.redhat.com/ubi8/openjdk-17\nCOPY app1.war /deployments/\n"

RELEASES: Dict[str, Dict[str, str]] = {
    # [1] service image changed -> new tag
    "S1-docker-build": {
        "App/services/app-1/image/Dockerfile": DOCKERFILE,
        "App/services/app-1/image/app1.war": "build 2",
    },
    # [2] field changes only
    "S2-field-update": {
        "App/openshift/yamls/deployment.yaml": dumps(APP_1_UPDATE),
    },
    # [3] image build + field changes on the same Deployment
    "S3-build-and-fields": {
        "App/services/app-1/image/Dockerfile": DOCKERFILE,
        "App/services/app-1/image/app1.war": "build 2",
        "App/openshift/yamls/deployment.yaml": dumps(APP_1_UPDATE),
    },
    # [4] scripts-only package: image tags from image_transfer.sh
    "S4-transfer-only": {
        "scripts/deploy/image_transfer.sh": transfer_script("1.5.0"),
        "scripts/deploy/apply_yaml.sh": apply_script(""),
        "scripts/app1/deployment.yaml": dumps(ENVIRONMENT["app1"]),
    },
    # [5] App-Published: field changes + image_transfer.sh
    "S5-published-transfer-and-fields": {
        "App-Published/App/yamls/deployment.yaml": dumps(APP1_UPDATE),
        "App-Published/scripts/deploy/image_transfer.sh": transfer_script("1.6.0"),
        "App-Published/scripts/deploy/apply_yaml.sh": apply_script("App-Published/"),
        "App-Published/scripts/app1/deployment.yaml": dumps(ENVIRONMENT["app1"]),
    },
    # [6] new Deployment (CREATE) + changed full Deployment (skipped)
    "S6-create-and-whole-file": {
        "App/openshift/yamls/app-3.yaml": dumps(
            deployment("app-3", "api", "quay.io/sacakti/app-3:1.0.0"),
        ),
        "App/openshift/yamls/app-2.yaml": dumps(
            deployment("app-2", "web", "quay.io/sacakti/app-2:1.1.0"),
        ),
    },
}


# ----------------------------------------------------------------------
# Sandbox
# ----------------------------------------------------------------------


def yaml_repository(path: Path) -> None:
    index: Dict[str, Any] = {"resources": {"Deployment": {}}, "deployments": {}}
    for name, document in ENVIRONMENT.items():
        file = f"deployments/{name}.yaml"
        (path / "deployments").mkdir(parents=True, exist_ok=True)
        (path / file).write_text(dumps(document))
        container = document["spec"]["template"]["spec"]["containers"][0]
        index["resources"]["Deployment"][name] = {"file": file}
        index["deployments"][file] = {
            "deployment": name,
            "containers": {container["name"]: {"image": container["image"]}},
        }
    (path / ".entropy").mkdir()
    (path / ".entropy" / "resource_index.json").write_text(json.dumps(index, indent=2))


def release_zip(path: Path, files: Dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def prepare(sandbox: Path) -> None:
    if sandbox.exists():
        if not (sandbox / MARKER).exists():
            sys.exit(f"Refusing to replace '{sandbox}': it is not a release-scenarios sandbox.")
        shutil.rmtree(sandbox)
    sandbox.mkdir(parents=True)
    (sandbox / MARKER).write_text("Created by tests/test-data/release_scenarios/build.py\n")


def step(name: str, plugin: str, tag: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": name,
        "plugin": plugin,
        "enabled": True,
        "on_failure": "continue",
        "tags": [tag],
        "arguments": arguments,
    }


def context_step(scenario: str) -> Dict[str, Any]:
    tag = scenario.split("-", 1)[0]
    return step(
        f"{tag}_Context",
        "release.context_builder",
        tag,
        {
            "release": f"${{sandbox}}/releases/{scenario}.zip",
            "docker_repository": "${sandbox}/docker",
            "yaml_repository": f"${{sandbox}}/yamls/{tag}",
            "image_tag": "${image_tag}",
        },
    )


def deployment_step(tag: str) -> Dict[str, Any]:
    return step(
        f"{tag}_Deployment",
        "oc.deployment",
        tag,
        {
            "mode": "deployments",
            "repository": f"${{sandbox}}/yamls/{tag}",
            "deployments": f"${{steps.{tag}_Context.outputs.deployment.resources.deployments}}",
        },
    )


def transfer_step(scenario: str, scripts: str) -> Dict[str, Any]:
    tag = scenario.split("-", 1)[0]
    return step(
        f"{tag}_Transfer",
        "custom.image_transfer",
        tag,
        {
            "release": f"${{sandbox}}/releases/{scenario}.zip",
            "release_scripts_directory": scripts,
            "skip_docker": True,
            "force_remove_processed": True,
        },
    )


def workflow(sandbox: Path) -> Dict[str, Any]:
    steps = []
    for scenario in RELEASES:
        tag = scenario.split("-", 1)[0]
        steps.append(context_step(scenario))
        if tag == "S4":
            steps.append(transfer_step(scenario, "scripts/deploy"))
        if tag == "S5":
            steps.append(transfer_step(scenario, "App-Published/scripts/deploy"))
        steps.append(deployment_step(tag))
    steps.append(
        step(
            "S7_FolderMode",
            "oc.deployment",
            "S7",
            {
                "mode": "folder",
                "source": "${sandbox}/folder/updates",
                "target": "${sandbox}/folder/deployments",
            },
        ),
    )
    return {
        "name": "ReleaseScenarios",
        "version": "1.0.0",
        "description": (
            "release.context_builder -> custom.image_transfer -> oc.deployment "
            "scenarios S1-S7. Check results with verify.py."
        ),
        "variables": {"sandbox": str(sandbox), "image_tag": IMAGE_TAG},
        "steps": steps,
    }


def folder_mode(sandbox: Path) -> None:
    updates = sandbox / "folder" / "updates"
    deployments = sandbox / "folder" / "deployments"
    updates.mkdir(parents=True)
    deployments.mkdir(parents=True)
    for name, container in (("app-1", "app"), ("app-2", "web")):
        (deployments / f"{name}.yaml").write_text(dumps(ENVIRONMENT[name]))
        (updates / f"{name}.yaml").write_text(
            dumps(
                {
                    "apiVersion": "entropy/v1",
                    "kind": "DeploymentUpdate",
                    "target": {"kind": "Deployment", "name": name},
                    "operations": [
                        {
                            "action": "add",
                            "field": "env",
                            "container": container,
                            "value": {"name": "FOLDER_MODE", "value": "yes"},
                        },
                    ],
                },
            ),
        )


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    sandbox = Path(sys.argv[1]).expanduser().resolve()
    prepare(sandbox)

    docker_image = sandbox / "docker" / "app-1" / "image"
    docker_image.mkdir(parents=True)
    (docker_image / "Dockerfile").write_text(DOCKERFILE)
    (docker_image / "app1.war").write_text("build 1")

    (sandbox / "releases").mkdir()
    for scenario, files in RELEASES.items():
        release_zip(sandbox / "releases" / f"{scenario}.zip", files)
        yaml_repository(sandbox / "yamls" / scenario.split("-", 1)[0])

    folder_mode(sandbox)

    workflow_file = sandbox / "release-scenarios.json"
    workflow_file.write_text(json.dumps(workflow(sandbox), indent=4))

    print(f"Sandbox:  {sandbox}")
    print(f"Workflow: {workflow_file}")
    print(f"Run:      ent workflow run -f {workflow_file}")
    print(f"Verify:   python {Path(__file__).with_name('verify.py')} {sandbox}")


if __name__ == "__main__":
    main()
