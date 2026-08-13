from __future__ import annotations
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cm_secret_update.model import (
    ConfigMapSecretUpdate,
)
from cm_secret_update.plugin import (
    CMSecretUpdateException,
    CmSecretUpdatePlugin,
)
from cm_secret_update.updater import (
    UpdateError,
    UpdateResult,
    UpdateSummary,
)
from unittest.mock import MagicMock, Mock
from lib.plugins.arguments import PluginArguments

class _TestContext:
    def __init__(
        self,
        arguments: dict,
    ) -> None:

        self.arguments = PluginArguments(
            arguments,
        )

        self.filesystem = Mock()
        self.message = Mock()
        self.outputs = {}

        self.activity_context = MagicMock()

        self.activity = Mock(
            return_value=self.activity_context,
        )


def _plugin(
    *,
    source: str = "/source",
    target: str = "/target",
    replace: bool = False,
) -> CmSecretUpdatePlugin:

    context = _TestContext(
        {
            "source": source,
            "target": target,
            "replace": replace,
        },
    )

    return CmSecretUpdatePlugin(
        context,
    )

def _result(
    *,
    kind: str = "ConfigMap",
    name: str = "application-config",
    path: Path = Path("/target/config.yaml"),
    created: bool = False,
    changes: list[dict] | None = None,
) -> UpdateResult:

    return UpdateResult(
        kind=kind,
        name=name,
        path=path,
        created=created,
        changes=changes or [],
    )


def _summary(
    *,
    results: list[UpdateResult] | None = None,
    errors: list[UpdateError] | None = None,
) -> UpdateSummary:

    results = results or []
    errors = errors or []

    return UpdateSummary(
        results=results,
        errors=errors,
    )


def test_execute_success() -> None:
    plugin = _plugin()

    summary = _summary(
        results=[
            _result(
                changes=[
                    {
                        "action": "update",
                        "key": "environment",
                    },
                ],
            ),
        ],
    )

    with patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretUpdateLoader",
    ) as source_loader_class, patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretTargetLoader",
    ) as target_loader_class, patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretUpdater",
    ) as updater_class:

        source_loader_class.return_value.load_directory.return_value = [
            Mock(spec=ConfigMapSecretUpdate),
        ]

        target_loader_class.return_value.load_directory.return_value = [
            Mock(),
        ]

        updater_class.return_value.update.return_value = summary

        plugin._execute()

    assert plugin.outputs["success"] is True
    assert plugin.outputs["failed"] is False

    assert plugin.outputs["resources_processed"] == 1
    assert plugin.outputs["resources_succeeded"] == 1
    assert plugin.outputs["resources_failed"] == 0
    assert plugin.outputs["changes"] == 1
    assert plugin.outputs["errors"] == []

    updater_class.return_value.update.assert_called_once()


def test_execute_partial_failure_sets_outputs_and_raises() -> None:
    plugin = _plugin()

    error = UpdateError(
        kind="Secret",
        name="application-secret",
        path=Path("/target/secret.yaml"),
        key="old_password",
        message="Cannot delete key 'old_password': key does not exist.",
    )

    summary = _summary(
        results=[
            _result(
                changes=[
                    {
                        "action": "update",
                        "key": "environment",
                    },
                ],
            ),
        ],
        errors=[
            error,
        ],
    )

    with patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretUpdateLoader",
    ) as source_loader_class, patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretTargetLoader",
    ) as target_loader_class, patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretUpdater",
    ) as updater_class:

        source_loader_class.return_value.load_directory.return_value = [
            Mock(spec=ConfigMapSecretUpdate),
        ]

        target_loader_class.return_value.load_directory.return_value = [
            Mock(),
        ]

        updater_class.return_value.update.return_value = summary

        with pytest.raises(
            CMSecretUpdateException,
            match="One or more ConfigMap/Secret updates failed.",
        ):
            plugin._execute()

    assert plugin.outputs["success"] is False
    assert plugin.outputs["failed"] is True

    assert plugin.outputs["resources_processed"] == 1
    assert plugin.outputs["resources_succeeded"] == 1
    assert plugin.outputs["resources_failed"] == 1
    assert plugin.outputs["changes"] == 1

    assert plugin.outputs["errors"] == [
        {
            "kind": "Secret",
            "name": "application-secret",
            "path": "/target/secret.yaml",
            "key": "old_password",
            "message": (
                "Cannot delete key 'old_password': "
                "key does not exist."
            ),
        },
    ]


def test_execute_passes_replace_false() -> None:
    plugin = _plugin(
        replace=False,
    )

    summary = _summary()

    with patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretUpdateLoader",
    ) as source_loader_class, patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretTargetLoader",
    ) as target_loader_class, patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretUpdater",
    ) as updater_class:

        definitions = [
            Mock(spec=ConfigMapSecretUpdate),
        ]

        resources = [
            Mock(),
        ]

        source_loader_class.return_value.load_directory.return_value = (
            definitions
        )

        target_loader_class.return_value.load_directory.return_value = (
            resources
        )

        updater_class.return_value.update.return_value = summary

        plugin._execute()

        updater_class.return_value.update.assert_called_once_with(
            definitions,
            resources,
            target_directory=Path("/target"),
            replace=False,
        )


def test_execute_passes_replace_true() -> None:
    plugin = _plugin(
        replace=True,
    )

    summary = _summary()

    with patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretUpdateLoader",
    ) as source_loader_class, patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretTargetLoader",
    ) as target_loader_class, patch(
        "cm_secret_update.plugin."
        "ConfigMapSecretUpdater",
    ) as updater_class:

        definitions = [
            Mock(spec=ConfigMapSecretUpdate),
        ]

        resources = [
            Mock(),
        ]

        source_loader_class.return_value.load_directory.return_value = (
            definitions
        )

        target_loader_class.return_value.load_directory.return_value = (
            resources
        )

        updater_class.return_value.update.return_value = summary

        plugin._execute()

        updater_class.return_value.update.assert_called_once_with(
            definitions,
            resources,
            target_directory=Path("/target"),
            replace=True,
        )


def test_invalid_replace_argument() -> None:
    plugin = _plugin()

    plugin.arguments["replace"] = "true"

    with pytest.raises(
        CMSecretUpdateException,
        match="Argument 'replace' must be a boolean.",
    ):
        plugin._replace()


def test_missing_source_argument() -> None:
    plugin = _plugin()

    del plugin.arguments["source"]

    with pytest.raises(
        CMSecretUpdateException,
        match="Argument 'source' must be a non-empty path.",
    ):
        plugin._required_path("source")


def test_missing_target_argument() -> None:
    plugin = _plugin()

    del plugin.arguments["target"]

    with pytest.raises(
        CMSecretUpdateException,
        match="Argument 'target' must be a non-empty path.",
    ):
        plugin._required_path("target")
