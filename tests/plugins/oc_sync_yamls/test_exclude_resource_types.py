"""
Tests for oc.sync_yamls leaving out whole resource types.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from lib.plugins import contract
from resources.plugins.oc.sync_yamls.exceptions import SyncYamlsPluginException
from resources.plugins.oc.sync_yamls.plugin import SyncYamlsPlugin

PLUGIN = Path(__file__).resolve().parents[3] / "resources" / "plugins" / "oc" / "sync_yamls"


def test_all_types_without_exclusions() -> None:
    assert SyncYamlsPlugin._resource_types([]) == SyncYamlsPlugin.RESOURCE_TYPES
    assert SyncYamlsPlugin._resource_types(None) == SyncYamlsPlugin.RESOURCE_TYPES


def test_excluded_types_are_left_out_in_order() -> None:
    assert SyncYamlsPlugin._resource_types(["Secrets", "routes"]) == (
        "deployments",
        "configmaps",
        "services",
    )


@pytest.mark.parametrize("excluded", [["pods"], [5]])
def test_rejects_unknown_types(excluded) -> None:
    with pytest.raises(SyncYamlsPluginException, match="exclude_resource_types"):
        SyncYamlsPlugin._resource_types(excluded)


def test_rejects_excluding_everything() -> None:
    with pytest.raises(SyncYamlsPluginException, match="no resource type"):
        SyncYamlsPlugin._resource_types(list(SyncYamlsPlugin.RESOURCE_TYPES))


def _plugin() -> SyncYamlsPlugin:
    return SyncYamlsPlugin(Mock())


def test_access_is_checked_only_for_synchronized_types() -> None:
    plugin = _plugin()
    answer = SimpleNamespace(failed=False, stdout="yes\n", stderr="")

    with patch.object(SyncYamlsPlugin, "_oc", return_value=answer) as oc:
        plugin._verify_namespace_access(
            namespace="sit",
            kubeconfig=Path("/k"),
            resource_types=("deployments", "configmaps"),
        )

    checked = [call.args[0][3] for call in oc.call_args_list]
    assert checked == ["deployments", "configmaps"]


def test_excluded_types_are_not_fetched() -> None:
    plugin = _plugin()

    with patch.object(SyncYamlsPlugin, "_sync_resource_type", return_value=[]) as sync:
        resources = plugin._sync_resources(
            repository=Path("/repo"),
            namespace="sit",
            structure={},
            ignore_resources={},
            resource_index={},
            kubeconfig=Path("/k"),
            resource_types=("deployments", "services"),
        )

    assert resources == {"deployments": [], "services": []}
    assert [call.kwargs["resource_type"] for call in sync.call_args_list] == [
        "deployments",
        "services",
    ]


def test_contract_takes_checked_types_as_a_list() -> None:
    declared = contract.declared(contract.read_manifest(PLUGIN))
    base = {"kubeconfig": "/k", "namespace": "sit", "yaml_repository": "/r"}

    checked = contract.check_arguments(declared, {**base, "exclude_resource_types": ["SECRETS"]})
    assert checked["exclude_resource_types"] == ["secrets"]
    assert contract.check_arguments(declared, base)["exclude_resource_types"] == []

    with pytest.raises(contract.ContractError) as caught:
        contract.check_arguments(declared, {**base, "exclude_resource_types": ["pods"]})
    assert "(not pods)" in caught.value.problems[0]
