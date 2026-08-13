from __future__ import annotations

import base64

import pytest

from cm_secret_update.engine import ConfigMapSecretUpdateEngine
from cm_secret_update.exceptions import (
    UpdateKeyAlreadyExistsError,
    UpdateKeyNotFoundError,
)
from cm_secret_update.model import (
    ConfigMapSecretUpdate,
    UpdateOperation,
    UpdateTarget,
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


def _engine() -> ConfigMapSecretUpdateEngine:
    return ConfigMapSecretUpdateEngine(
        yaml_loader=lambda value: {},
        yaml_dumper=lambda value: "",
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


def _secret() -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "application-secret",
        },
        "data": {
            "username": base64.b64encode(
                b"admin",
            ).decode("ascii"),
        },
    }


def test_add_missing_key() -> None:
    target = _configmap()

    definition = _definition(
        operations=[
            UpdateOperation(
                action="add",
                key="new.setting",
                value="enabled",
            ),
        ],
    )

    changes = _engine().apply(
        target,
        definition,
    )

    assert target["data"]["new.setting"] == "enabled"
    assert changes == [
        {
            "action": "add",
            "key": "new.setting",
        },
    ]


def test_add_existing_key_fails_without_replace() -> None:
    target = _configmap()

    definition = _definition(
        operations=[
            UpdateOperation(
                action="add",
                key="environment",
                value="uat",
            ),
        ],
    )

    with pytest.raises(
        UpdateKeyAlreadyExistsError,
        match="key already exists",
    ):
        _engine().apply(
            target,
            definition,
        )


def test_update_existing_key() -> None:
    target = _configmap()

    definition = _definition(
        operations=[
            UpdateOperation(
                action="update",
                key="environment",
                value="uat",
            ),
        ],
    )

    changes = _engine().apply(
        target,
        definition,
    )

    assert target["data"]["environment"] == "uat"
    assert changes == [
        {
            "action": "update",
            "key": "environment",
        },
    ]


def test_update_missing_key_fails() -> None:
    target = _configmap()

    definition = _definition(
        operations=[
            UpdateOperation(
                action="update",
                key="missing",
                value="value",
            ),
        ],
    )

    with pytest.raises(
        UpdateKeyNotFoundError,
        match="key does not exist",
    ):
        _engine().apply(
            target,
            definition,
        )


def test_delete_existing_key() -> None:
    target = _configmap()

    definition = _definition(
        operations=[
            UpdateOperation(
                action="delete",
                key="environment",
            ),
        ],
    )

    changes = _engine().apply(
        target,
        definition,
    )

    assert "environment" not in target["data"]
    assert changes == [
        {
            "action": "delete",
            "key": "environment",
            "status": "deleted",
        },
    ]

def test_delete_missing_key_fails() -> None:
    target = _configmap()

    definition = _definition(
        operations=[
            UpdateOperation(
                action="delete",
                key="missing",
            ),
        ],
    )

    with pytest.raises(
        UpdateKeyNotFoundError,
        match="key does not exist",
    ):
        _engine().apply(
            target,
            definition,
        )


def test_replace_does_not_change_engine_add_semantics() -> None:
    """
    Replacement normalization belongs to the updater.

    The engine itself should still reject an existing key
    when given an add operation.
    """

    target = _configmap()

    definition = _definition(
        operations=[
            UpdateOperation(
                action="add",
                key="environment",
                value="uat",
            ),
        ],
    )

    with pytest.raises(
        UpdateKeyAlreadyExistsError,
    ):
        _engine().apply(
            target,
            definition,
            replace=True,
        )


def test_secret_update_decodes_and_reencodes_value() -> None:
    target = _secret()

    definition = _definition(
        kind="Secret",
        name="application-secret",
        operations=[
            UpdateOperation(
                action="update",
                key="username",
                value="admin2",
            ),
        ],
    )

    changes = _engine().apply(
        target,
        definition,
    )

    expected = base64.b64encode(
        b"admin2",
    ).decode("ascii")

    assert target["data"]["username"] == expected

    assert changes == [
        {
            "action": "update",
            "key": "username",
        },
    ]

def test_delete_missing_key_is_unchanged_with_replace() -> None:
    target = _configmap()

    definition = _definition(
        operations=[
            UpdateOperation(
                action="delete",
                key="missing",
            ),
        ],
    )

    changes = _engine().apply(
        target,
        definition,
        replace=True,
    )

    assert "missing" not in target["data"]

    assert changes == [
        {
            "action": "delete",
            "key": "missing",
            "status": "unchanged",
        },
    ]

def test_prune_removes_unmanaged_keys() -> None:
    target = _configmap()

    changes = _engine().prune(
        target,
        {
            "environment",
        },
    )

    assert target["data"] == {
        "environment": "sit",
    }

    assert changes == [
        {
            "action": "delete",
            "key": "existing.setting",
        },
    ]

def test_prune_keeps_managed_keys() -> None:
    target = _configmap()

    changes = _engine().prune(
        target,
        {
            "environment",
            "existing.setting",
        },
    )

    assert target["data"] == {
        "environment": "sit",
        "existing.setting": "original",
    }

    assert changes == []

def test_prune_empty_target() -> None:
    target = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "application-config",
        },
        "data": {},
    }

    changes = _engine().prune(
        target,
        {
            "environment",
        },
    )

    assert changes == []
    assert target["data"] == {}


