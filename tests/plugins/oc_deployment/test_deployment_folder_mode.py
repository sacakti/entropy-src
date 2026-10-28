"""
Tests for oc.deployment in folder mode with several DeploymentUpdate files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import yaml

from lib.executor import LinuxExecutor
from lib.plugins.arguments import PluginArguments
from resources.plugins.oc.deployment.plugin import DeploymentPlugin


def _deployment(name: str) -> dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {
                    "containers": [{"name": "app", "image": f"quay.io/sacakti/{name}:1.0.0"}],
                },
            },
        },
    }


def _update(name: str) -> dict[str, Any]:
    return {
        "apiVersion": "entropy/v1",
        "kind": "DeploymentUpdate",
        "target": {"kind": "Deployment", "name": name},
        "operations": [
            {
                "action": "add",
                "field": "env",
                "container": "app",
                "value": {"name": "APP_MODE", "value": name},
            },
        ],
    }


def _env(path: Path) -> list[dict[str, Any]]:
    document = yaml.safe_load(path.read_text())
    return document["spec"]["template"]["spec"]["containers"][0]["env"]


def test_every_update_definition_is_applied(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    for name in ("app-1", "app-2", "app-3"):
        (source / f"{name}.yaml").write_text(yaml.safe_dump(_update(name)))
        (target / f"{name}.yaml").write_text(yaml.safe_dump(_deployment(name)))

    context = MagicMock()
    context.arguments = PluginArguments(
        {"mode": "folder", "source": str(source), "target": str(target)},
    )
    context.filesystem = LinuxExecutor()
    context.outputs = {}
    context.artifacts = {}

    result = DeploymentPlugin(context).execute()

    assert result.success, result.errors
    assert result.outputs["resources_succeeded"] == 3
    for name in ("app-1", "app-2", "app-3"):
        assert _env(target / f"{name}.yaml") == [{"name": "APP_MODE", "value": name}]
