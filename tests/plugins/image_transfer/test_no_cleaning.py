"""custom.image_transfer leaves cleaning Docker storage to docker.clean."""

from __future__ import annotations

import json
import zipfile
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lib.executor import LinuxExecutor
from lib.plugins.arguments import PluginArguments
from lib.plugins.contract import check_arguments, check_source, declared, read_manifest
from resources.plugins.custom.image_transfer.plugin import ImageTransferPlugin

DIRECTORY = (
    Path(__file__).resolve().parents[3] / "resources" / "plugins" / "custom" / "image_transfer"
)
GIB = 1024**3


def _shell(free_gb: float) -> tuple:
    commands = []

    def run(command, **options):
        commands.append(list(command))
        stdout = ""
        if command[:2] == ["docker", "info"]:
            stdout = "/var/lib/docker\n"
        elif command[0] == "df":
            kib = int(free_gb * GIB / 1024)
            stdout = (
                f"Filesystem 1024-blocks Used Available Capacity Mounted\n/dev/x 9 9 {kib} 9% /\n"
            )
        return SimpleNamespace(
            success=True, failed=False, exit_code=0, stdout=stdout, stderr="", command=command
        )

    return run, commands


def _plugin(free_gb: float, **arguments) -> tuple:
    context = MagicMock()
    context.outputs = {}
    context.arguments = PluginArguments(arguments)
    run, commands = _shell(free_gb)
    context.shell.run.side_effect = run
    return ImageTransferPlugin(context), context, commands


def test_short_storage_fails_and_says_where_to_clean() -> None:
    plugin, _, commands = _plugin(1)

    with pytest.raises(RuntimeError, match="docker.clean"):
        plugin._check_docker_storage(10)

    assert not any(item[:2] in (["docker", "rmi"], ["docker", "images"]) for item in commands)
    assert not any(item[:2] == ["docker", "builder"] for item in commands)


def test_enough_storage_passes_and_cleans_nothing() -> None:
    plugin, _, commands = _plugin(50)

    assert plugin._check_docker_storage(10) == 50 * GIB

    assert not any(item[:2] in (["docker", "rmi"], ["docker", "builder"]) for item in commands)


def test_no_cleaning_code_is_left() -> None:
    source = (DIRECTORY / "plugin.py").read_text(encoding="utf-8")

    for command in ('"rmi"', '"prune"', '"builder"', "_cleanup_old_images", "cleanup_performed"):
        assert command not in source


def test_the_installer_accepts_the_contract() -> None:
    contract = declared(read_manifest(DIRECTORY))

    assert contract is not None
    assert check_source(DIRECTORY, contract) == []


@pytest.mark.parametrize(
    "values",
    [
        {"old_image_pattern": ":25.01.01."},
        {"cleanup_builder_cache": False},
        {"old_image_pattern": "x", "cleanup_builder_cache": True},
    ],
)
def test_workflows_that_still_set_the_old_arguments_are_not_refused(values) -> None:
    contract = declared(read_manifest(DIRECTORY))

    checked = check_arguments(contract, {"release": "/r/H1.zip", **values})

    for name, value in values.items():
        assert checked[name] == value


def test_the_old_arguments_have_no_default_so_a_warning_means_a_workflow_set_them() -> None:
    contract = declared(read_manifest(DIRECTORY))

    checked = check_arguments(contract, {"release": "/r/H1.zip"})

    assert checked.get("old_image_pattern") is None
    assert checked.get("cleanup_builder_cache") is None


def test_the_example_workflow_does_not_use_them() -> None:
    workflow = json.loads((DIRECTORY / "workflow.json").read_text(encoding="utf-8"))

    for step in workflow["steps"]:
        assert "old_image_pattern" not in step["arguments"]
        assert "cleanup_builder_cache" not in step["arguments"]


# ----------------------------------------------------------------------
# A whole run, with real files and Docker recorded
# ----------------------------------------------------------------------

TRANSFER = """#!/bin/bash
docker login azure.example.com $1 $2
docker pull azure.example.com/a:1
docker tag azure.example.com/a:1 quay.example.com/a:1
docker push quay.example.com/a:1
"""
APPLY = "oc apply -f /home/devops/H1/yamls/\n"


def _run(tmp_path: Path, free_gb: float, **arguments) -> tuple:
    release = tmp_path / "H1.zip"
    with zipfile.ZipFile(release, "w") as archive:
        archive.writestr("scripts/deploy/image_transfer.sh", TRANSFER)
        archive.writestr("scripts/deploy/apply_yaml.sh", APPLY)
        archive.writestr("yamls/a.yaml", "kind: Deployment\n")

    executor = LinuxExecutor()
    context = MagicMock()
    context.outputs = {}
    context.artifacts = {}
    context.activity.return_value = nullcontext()
    context.filesystem = executor
    context.archive = executor
    # As the runner does: defaults come from the contract.
    context.arguments = PluginArguments(
        check_arguments(
            declared(read_manifest(DIRECTORY)),
            {"release": str(release), "validate_yaml": False, **arguments},
        )
    )
    run, commands = _shell(free_gb)
    context.shell.run.side_effect = run
    return ImageTransferPlugin(context).execute(), context, commands


def _docker(commands: list) -> list:
    return [item[1] for item in commands if item[0] == "docker"]


def test_a_run_with_enough_space_transfers_and_cleans_nothing(tmp_path) -> None:
    result, context, commands = _run(tmp_path, 50)

    assert result.success, result.errors
    assert _docker(commands)[-4:] == ["login", "pull", "tag", "push"]
    assert not {"rmi", "images", "builder"} & set(_docker(commands))
    assert "cleanup_performed" not in context.outputs
    assert "old_image_pattern" not in context.outputs["configuration"]
    context.message.warning.assert_not_called()


def test_a_run_short_of_space_stops_before_any_transfer(tmp_path) -> None:
    result, _, commands = _run(tmp_path, 1)

    assert not result.success
    assert "docker.clean" in str(result.errors)
    assert not {"rmi", "builder", "pull", "push"} & set(_docker(commands))


def test_a_workflow_setting_the_old_arguments_is_warned_and_nothing_is_cleaned(tmp_path) -> None:
    result, context, commands = _run(
        tmp_path, 50, old_image_pattern=":25.01.01.", cleanup_builder_cache=True
    )

    assert result.success, result.errors
    warnings = [str(call.args[0]) for call in context.message.warning.call_args_list]
    assert any("'old_image_pattern' is ignored" in item for item in warnings)
    assert any("'cleanup_builder_cache' is ignored" in item for item in warnings)
    assert not {"rmi", "builder"} & set(_docker(commands))
