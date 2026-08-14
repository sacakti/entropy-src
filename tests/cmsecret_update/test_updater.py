from __future__ import annotations

from pathlib import Path

from cm_secret_update.engine import ConfigMapSecretUpdateEngine
from cm_secret_update.model import (
    ConfigMapSecretUpdate,
    UpdateOperation,
    UpdateTarget,
)
from cm_secret_update.target_loader import (
    TargetFile,
    TargetResource,
)
from cm_secret_update.updater import (
    ConfigMapSecretUpdater,
)


class FakeFilesystem:
    """
    Minimal filesystem implementation required by the updater.
    """

    def __init__(self) -> None:
        self.files: dict[Path, str] = {}

    def exists(
        self,
        path: Path,
    ) -> bool:
        return path in self.files

    def write_text(
        self,
        path: Path,
        data: str,
    ) -> None:
        self.files[path] = data

    def serialize_yaml_documents(
        self,
        documents,
    ) -> str:
        return str(documents)


def _engine() -> ConfigMapSecretUpdateEngine:
    return ConfigMapSecretUpdateEngine()


def _filesystem() -> FakeFilesystem:
    return FakeFilesystem()


def _updater(
    filesystem: FakeFilesystem | None = None,
) -> ConfigMapSecretUpdater:
    if filesystem is None:
        filesystem = _filesystem()

    return ConfigMapSecretUpdater(
        engine=_engine(),
        filesystem=filesystem,
    )


def _definition(
    *,
    kind: str = "ConfigMap",
    name: str = "application-config",
    operations: list[UpdateOperation],
) -> ConfigMapSecretUpdate:
    return ConfigMapSecretUpdate(
        api_version="entropy/v1",
        kind="ConfigMapSecretUpdate",
        target=UpdateTarget(
            kind=kind,
            name=name,
        ),
        operations=operations,
    )


def _resource(
    document: dict,
    path: str = "/target/app.yaml",
) -> TargetResource:
    target_file = TargetFile(
        path=Path(path),
        documents=[document],
    )

    return TargetResource(
        kind=document["kind"],
        name=document["metadata"]["name"],
        document=document,
        target_file=target_file,
        document_index=0,
    )


def _configmap() -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "application-config",
        },
        "data": {
            "environment": "sit",
            "existing.setting": "original",
        },
    }


def test_updates_existing_resource() -> None:
    document = _configmap()

    resource = _resource(
        document,
    )

    definition = _definition(
        operations=[
            UpdateOperation(
                action="update",
                key="environment",
                value="uat",
            ),
        ],
    )

    filesystem = _filesystem()

    summary = _updater(
        filesystem,
    ).update(
        [definition],
        [resource],
        target_directory=Path("/target"),
        replace=False,
    )

    assert summary.resources_processed == 1
    assert summary.resources_succeeded == 1
    assert summary.resources_failed == 0
    assert summary.failed is False
    assert summary.changes_count == 1

    assert document["data"]["environment"] == "uat"

    assert summary.results[0].kind == "ConfigMap"
    assert summary.results[0].name == "application-config"
    assert summary.results[0].created is False


def test_creates_missing_resource() -> None:
    definition = _definition(
        operations=[
            UpdateOperation(
                action="add",
                key="environment",
                value="uat",
            ),
        ],
    )

    filesystem = _filesystem()

    summary = _updater(
        filesystem,
    ).update(
        [definition],
        [],
        target_directory=Path("/target"),
        replace=False,
    )

    assert summary.resources_processed == 1
    assert summary.resources_succeeded == 1
    assert summary.resources_failed == 0
    assert summary.failed is False

    result = summary.results[0]

    assert result.created is True
    assert result.kind == "ConfigMap"
    assert result.name == "application-config"

    expected_path = Path("/target") / "configmap-application-config.yaml"

    assert result.path == expected_path
    assert expected_path in filesystem.files


def test_replace_converts_existing_add_to_update() -> None:
    document = _configmap()

    resource = _resource(
        document,
    )

    definition = _definition(
        operations=[
            UpdateOperation(
                action="add",
                key="environment",
                value="uat",
            ),
        ],
    )

    summary = _updater().update(
        [definition],
        [resource],
        target_directory=Path("/target"),
        replace=True,
    )

    assert summary.resources_succeeded == 1
    assert summary.resources_failed == 0
    assert summary.failed is False

    assert document["data"]["environment"] == "uat"

    assert summary.results[0].changes == [
        {
            "action": "update",
            "key": "environment",
            "status": "replaced_add",
        },
        {
            "action": "delete",
            "key": "existing.setting",
        },
    ]


def test_replace_missing_delete_is_unchanged() -> None:
    document = _configmap()

    resource = _resource(
        document,
    )

    definition = _definition(
        operations=[
            UpdateOperation(
                action="delete",
                key="missing",
            ),
        ],
    )

    summary = _updater().update(
        [definition],
        [resource],
        target_directory=Path("/target"),
        replace=True,
    )

    assert summary.resources_succeeded == 1
    assert summary.resources_failed == 0
    assert summary.failed is False

    assert summary.results[0].changes == [
        {
            "action": "delete",
            "key": "missing",
            "status": "unchanged",
        },
        {
            "action": "delete",
            "key": "environment",
        },
        {
            "action": "delete",
            "key": "existing.setting",
        },
    ]


def test_replace_prunes_unmanaged_keys() -> None:
    document = _configmap()

    resource = _resource(
        document,
    )

    definition = _definition(
        operations=[
            UpdateOperation(
                action="update",
                key="environment",
                value="uat",
            ),
        ],
    )

    summary = _updater().update(
        [definition],
        [resource],
        target_directory=Path("/target"),
        replace=True,
    )

    assert summary.resources_succeeded == 1
    assert summary.resources_failed == 0
    assert summary.failed is False

    assert document["data"] == {
        "environment": "uat",
    }

    assert summary.changes_count == 2

    assert summary.results[0].changes == [
        {
            "action": "update",
            "key": "environment",
        },
        {
            "action": "delete",
            "key": "existing.setting",
        },
    ]


def test_replace_keeps_all_managed_keys() -> None:
    document = _configmap()

    resource = _resource(
        document,
    )

    definition = _definition(
        operations=[
            UpdateOperation(
                action="update",
                key="environment",
                value="uat",
            ),
            UpdateOperation(
                action="update",
                key="existing.setting",
                value="updated",
            ),
        ],
    )

    summary = _updater().update(
        [definition],
        [resource],
        target_directory=Path("/target"),
        replace=True,
    )

    assert summary.resources_succeeded == 1
    assert summary.resources_failed == 0
    assert summary.failed is False

    assert document["data"] == {
        "environment": "uat",
        "existing.setting": "updated",
    }

    assert summary.changes_count == 2


def test_failed_resource_is_aggregated() -> None:
    document = _configmap()

    resource = _resource(
        document,
    )

    definition = _definition(
        operations=[
            UpdateOperation(
                action="update",
                key="missing",
                value="value",
            ),
        ],
    )

    summary = _updater().update(
        [definition],
        [resource],
        target_directory=Path("/target"),
        replace=False,
    )

    assert summary.resources_processed == 1
    assert summary.resources_succeeded == 0
    assert summary.resources_failed == 1
    assert summary.failed is True
    assert summary.changes_count == 0

    assert len(summary.results) == 0
    assert len(summary.errors) == 1

    error = summary.errors[0]

    assert error.kind == "ConfigMap"
    assert error.name == "application-config"
    assert error.key == "missing"


def test_one_resource_failure_does_not_stop_other_resources() -> None:
    configmap = _configmap()

    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "application-secret",
        },
        "data": {
            "username": "YWRtaW4=",
        },
    }

    resources = [
        _resource(
            configmap,
            "/target/config.yaml",
        ),
        _resource(
            secret,
            "/target/secret.yaml",
        ),
    ]

    definitions = [
        _definition(
            kind="ConfigMap",
            name="application-config",
            operations=[
                UpdateOperation(
                    action="update",
                    key="environment",
                    value="uat",
                ),
            ],
        ),
        _definition(
            kind="Secret",
            name="application-secret",
            operations=[
                UpdateOperation(
                    action="delete",
                    key="missing",
                ),
            ],
        ),
    ]

    summary = _updater().update(
        definitions,
        resources,
        target_directory=Path("/target"),
        replace=False,
    )

    assert summary.resources_processed == 2
    assert summary.resources_succeeded == 1
    assert summary.resources_failed == 1
    assert summary.failed is True

    assert summary.changes_count == 1

    assert len(summary.results) == 1
    assert summary.results[0].kind == "ConfigMap"

    assert len(summary.errors) == 1
    assert summary.errors[0].kind == "Secret"

    assert configmap["data"]["environment"] == "uat"
