from pathlib import Path

from cm_secret_update.index import (
    ConfigMapSecretTargetIndex,
)
from cm_secret_update.target_loader import (
    TargetFile,
    TargetResource,
)


def _resource(
    kind: str,
    name: str,
) -> TargetResource:
    document = {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {
            "name": name,
        },
        "data": {},
    }

    target_file = TargetFile(
        path=Path(
            f"/target/{name}.yaml",
        ),
        documents=[
            document,
        ],
    )

    return TargetResource(
        kind=kind,
        name=name,
        document=document,
        target_file=target_file,
        document_index=0,
    )


def test_get_existing_resource() -> None:
    configmap = _resource(
        "ConfigMap",
        "application-config",
    )

    secret = _resource(
        "Secret",
        "application-secret",
    )

    index = ConfigMapSecretTargetIndex(
        [
            configmap,
            secret,
        ],
    )

    assert (
        index.get(
            "ConfigMap",
            "application-config",
        )
        is configmap
    )

    assert (
        index.get(
            "Secret",
            "application-secret",
        )
        is secret
    )


def test_get_missing_resource_returns_none() -> None:
    resource = _resource(
        "ConfigMap",
        "application-config",
    )

    index = ConfigMapSecretTargetIndex(
        [
            resource,
        ],
    )

    assert (
        index.get(
            "ConfigMap",
            "missing",
        )
        is None
    )


def test_kind_is_part_of_identity() -> None:
    configmap = _resource(
        "ConfigMap",
        "application",
    )

    secret = _resource(
        "Secret",
        "application",
    )

    index = ConfigMapSecretTargetIndex(
        [
            configmap,
            secret,
        ],
    )

    assert (
        index.get(
            "ConfigMap",
            "application",
        )
        is configmap
    )

    assert (
        index.get(
            "Secret",
            "application",
        )
        is secret
    )


def test_contains_existing_resource() -> None:
    resource = _resource(
        "ConfigMap",
        "application-config",
    )

    index = ConfigMapSecretTargetIndex(
        [
            resource,
        ],
    )

    assert (
        index.contains(
            "ConfigMap",
            "application-config",
        )
        is True
    )


def test_contains_missing_resource() -> None:
    resource = _resource(
        "ConfigMap",
        "application-config",
    )

    index = ConfigMapSecretTargetIndex(
        [
            resource,
        ],
    )

    assert (
        index.contains(
            "ConfigMap",
            "missing",
        )
        is False
    )


def test_resources_returns_all_indexed_resources() -> None:
    configmap = _resource(
        "ConfigMap",
        "application-config",
    )

    secret = _resource(
        "Secret",
        "application-secret",
    )

    index = ConfigMapSecretTargetIndex(
        [
            configmap,
            secret,
        ],
    )

    resources = index.resources()

    assert resources == [
        configmap,
        secret,
    ]


def test_resources_returns_new_list() -> None:
    configmap = _resource(
        "ConfigMap",
        "application-config",
    )

    index = ConfigMapSecretTargetIndex(
        [
            configmap,
        ],
    )

    resources = index.resources()

    resources.clear()

    assert index.resources() == [
        configmap,
    ]


def test_empty_index() -> None:
    index = ConfigMapSecretTargetIndex(
        [],
    )

    assert (
        index.get(
            "ConfigMap",
            "application-config",
        )
        is None
    )

    assert (
        index.contains(
            "ConfigMap",
            "application-config",
        )
        is False
    )

    assert index.resources() == []
