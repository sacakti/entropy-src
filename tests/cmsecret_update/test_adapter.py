from __future__ import annotations

import base64

import pytest

from cm_secret_update.adapter import (
    ConfigMapSecretTarget,
)
from cm_secret_update.exceptions import (
    UpdateTargetError,
)

def test_configmap_get_and_set() -> None:
    document = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "application-config",
        },
        "data": {
            "environment": "sit",
        },
    }

    target = ConfigMapSecretTarget(
        document,
        "ConfigMap",
    )

    assert target.contains("environment")
    assert target.get("environment") == "sit"

    target.set(
        "environment",
        "uat",
    )

    assert target.get("environment") == "uat"
    assert document["data"]["environment"] == "uat"


def test_configmap_add_and_delete() -> None:
    document = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "application-config",
        },
        "data": {},
    }

    target = ConfigMapSecretTarget(
        document,
        "ConfigMap",
    )

    target.set(
        "new.setting",
        "enabled",
    )

    assert target.contains("new.setting")

    target.delete(
        "new.setting",
    )

    assert not target.contains("new.setting")


def test_secret_get_decodes_base64() -> None:
    encoded = base64.b64encode(
        b"password123",
    ).decode("ascii")

    document = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "application-secret",
        },
        "data": {
            "password": encoded,
        },
    }

    target = ConfigMapSecretTarget(
        document,
        "Secret",
    )

    assert target.get(
        "password",
    ) == "password123"


def test_secret_set_encodes_base64() -> None:
    document = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "application-secret",
        },
        "data": {},
    }

    target = ConfigMapSecretTarget(
        document,
        "Secret",
    )

    target.set(
        "password",
        "password123",
    )

    expected = base64.b64encode(
        b"password123",
    ).decode("ascii")

    assert document["data"]["password"] == expected
    assert target.get("password") == "password123"


# def test_clear_removes_all_data() -> None:
#     document = {
#         "apiVersion": "v1",
#         "kind": "ConfigMap",
#         "metadata": {
#             "name": "application-config",
#         },
#         "data": {
#             "one": "1",
#             "two": "2",
#         },
#     }

#     target = ConfigMapSecretTarget(
#         document,
#         "ConfigMap",
#     )

#     target.clear()

#     assert target.keys() == set()
#     assert document["data"] == {}


def test_invalid_kind_is_rejected() -> None:
    document = {
        "apiVersion": "v1",
        "kind": "Deployment",
        "metadata": {
            "name": "application",
        },
        "data": {},
    }

    with pytest.raises(
        UpdateTargetError,
        match="Unsupported target kind",
    ):
        ConfigMapSecretTarget(
            document,
            "Deployment",
        )


def test_kind_mismatch_is_rejected() -> None:
    document = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "application-config",
        },
        "data": {},
    }

    with pytest.raises(
        UpdateTargetError,
        match="does not match expected",
    ):
        ConfigMapSecretTarget(
            document,
            "Secret",
        )
