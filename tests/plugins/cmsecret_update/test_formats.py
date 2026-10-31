"""
Engine coverage for every supported value format:
scalar key/value, properties, YAML, and JSON.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
import yaml
from cm_secret_update.engine import ConfigMapSecretUpdateEngine
from cm_secret_update.exceptions import (
    DeploymentUpdateTargetError,
    UpdateDefinitionError,
)
from cm_secret_update.model import (
    ConfigMapSecretUpdate,
    UpdateOperation,
    UpdateTarget,
)
from cm_secret_update.validator import ConfigMapSecretUpdateValidator


def _engine() -> ConfigMapSecretUpdateEngine:
    return ConfigMapSecretUpdateEngine(
        yaml_loader=yaml.safe_load,
        yaml_dumper=lambda value: yaml.safe_dump(
            value,
            sort_keys=False,
        ),
    )


def _definition(
    operations: list[UpdateOperation],
    kind: str = "ConfigMap",
) -> ConfigMapSecretUpdate:
    return ConfigMapSecretUpdate(
        api_version="entropy/v1",
        kind="ConfigMapSecretUpdate",
        target=UpdateTarget(
            kind=kind,
            name="app",
        ),
        operations=operations,
    )


def _configmap(data: dict[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "app"},
        "data": dict(data),
    }


def _secret(data: dict[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "app"},
        "type": "Opaque",
        "data": {key: base64.b64encode(value.encode()).decode() for key, value in data.items()},
    }


def _decoded(secret: dict[str, Any], key: str) -> str:
    return base64.b64decode(secret["data"][key]).decode()


# ----------------------------------------------------------------------
# Scalar key/value
# ----------------------------------------------------------------------


def test_scalar_update_and_add_configmap() -> None:
    target = _configmap({"environment": "sit"})

    changes = _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(action="update", key="environment", value="uat"),
                UpdateOperation(action="add", key="region", value="sg"),
            ],
        ),
    )

    assert target["data"] == {"environment": "uat", "region": "sg"}
    assert [change["status"] for change in changes] == ["updated", "added"]


def test_scalar_delete_configmap() -> None:
    target = _configmap({"environment": "sit", "obsolete": "x"})

    changes = _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(action="delete", key="obsolete"),
                UpdateOperation(action="delete", key="never-there"),
            ],
        ),
    )

    assert target["data"] == {"environment": "sit"}
    assert [change["status"] for change in changes] == ["deleted", "unchanged_missing"]


def test_scalar_update_secret_is_base64_encoded() -> None:
    target = _secret({"password": "old"})

    _engine().apply(
        target,
        _definition(
            [UpdateOperation(action="update", key="password", value="n3w")],
            kind="Secret",
        ),
    )

    assert _decoded(target, "password") == "n3w"


# ----------------------------------------------------------------------
# Properties
# ----------------------------------------------------------------------


def _properties_update(entries: dict[str, Any]) -> UpdateOperation:
    return UpdateOperation(
        action="update",
        key="application.properties",
        format="properties",
        entries=entries,
    )


def test_properties_added_on_new_line_when_content_lacks_trailing_newline() -> None:
    target = _configmap({"application.properties": "app.name=old\napp.port=8080"})

    _engine().apply(
        target,
        _definition([_properties_update({"app.port": "8081", "app.debug": "true"})]),
    )

    assert target["data"]["application.properties"] == (
        "app.name=old\napp.port=8081\napp.debug=true\n"
    )


def test_properties_added_after_trailing_newline_without_blank_line() -> None:
    target = _configmap({"application.properties": "app.name=old\n"})

    _engine().apply(
        target,
        _definition([_properties_update({"app.debug": "true", "app.port": "1"})]),
    )

    assert target["data"]["application.properties"] == (
        "app.name=old\napp.debug=true\napp.port=1\n"
    )


def test_properties_added_after_trailing_comment_without_newline() -> None:
    target = _configmap({"application.properties": "app.name=old\n# end"})

    _engine().apply(
        target,
        _definition([_properties_update({"app.debug": "true"})]),
    )

    assert target["data"]["application.properties"] == ("app.name=old\n# end\napp.debug=true\n")


def test_properties_added_keeps_crlf_line_endings() -> None:
    target = _configmap({"application.properties": "app.name=old\r\napp.port=8080"})

    _engine().apply(
        target,
        _definition([_properties_update({"app.debug": "true"})]),
    )

    assert target["data"]["application.properties"] == (
        "app.name=old\r\napp.port=8080\r\napp.debug=true\r\n"
    )


def test_properties_created_when_key_missing() -> None:
    target = _configmap({})

    _engine().apply(
        target,
        _definition([_properties_update({"a": "1", "b": "2"})]),
    )

    assert target["data"]["application.properties"] == "a=1\nb=2\n"


def test_properties_update_secret_without_trailing_newline() -> None:
    target = _secret({"db.properties": "db.user=app"})

    _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(
                    action="update",
                    key="db.properties",
                    format="properties",
                    entries={"db.password": "s3cret"},
                ),
            ],
            kind="Secret",
        ),
    )

    assert _decoded(target, "db.properties") == "db.user=app\ndb.password=s3cret\n"


def test_properties_delete_entries() -> None:
    target = _configmap({"application.properties": "a=1\nb=2\nc=3"})

    _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(
                    action="delete",
                    key="application.properties",
                    format="properties",
                    entries=["b"],
                ),
            ],
        ),
    )

    assert target["data"]["application.properties"] == "a=1\nc=3"


# ----------------------------------------------------------------------
# YAML
# ----------------------------------------------------------------------


def test_yaml_merge_update() -> None:
    target = _configmap(
        {"application.yaml": "server:\n  port: 8080\n  host: local\napp:\n  name: old\n"},
    )

    _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(
                    action="update",
                    key="application.yaml",
                    format="yaml",
                    entries={"server": {"port": 9090}, "app": {"debug": True}},
                ),
            ],
        ),
    )

    assert yaml.safe_load(target["data"]["application.yaml"]) == {
        "server": {"port": 9090, "host": "local"},
        "app": {"name": "old", "debug": True},
    }


def test_yaml_delete_paths() -> None:
    target = _configmap({"application.yaml": "server:\n  port: 8080\n  debug: true\n"})

    changes = _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(
                    action="delete",
                    key="application.yaml",
                    format="yaml",
                    entries=["server.debug", "server.missing"],
                ),
            ],
        ),
    )

    assert yaml.safe_load(target["data"]["application.yaml"]) == {"server": {"port": 8080}}
    assert [entry["status"] for entry in changes[0]["entries"]] == [
        "deleted",
        "unchanged_missing",
    ]


# ----------------------------------------------------------------------
# JSON
# ----------------------------------------------------------------------


def test_json_merge_update_configmap() -> None:
    target = _configmap(
        {"application.json": '{"server": {"port": 8080, "host": "local"}, "name": "old"}'},
    )

    _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(
                    action="update",
                    key="application.json",
                    format="json",
                    entries={"server": {"port": 9090}, "features": ["a", "b"]},
                ),
            ],
        ),
    )

    content = target["data"]["application.json"]

    assert json.loads(content) == {
        "server": {"port": 9090, "host": "local"},
        "name": "old",
        "features": ["a", "b"],
    }
    assert content.startswith('{\n  "server"')
    assert not content.endswith("\n")


def test_json_preserves_trailing_newline() -> None:
    target = _configmap({"application.json": '{"a": 1}\n'})

    _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(
                    action="update",
                    key="application.json",
                    format="json",
                    entries={"b": 2},
                ),
            ],
        ),
    )

    assert target["data"]["application.json"] == '{\n  "a": 1,\n  "b": 2\n}\n'


def test_json_created_when_key_missing() -> None:
    target = _configmap({})

    changes = _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(
                    action="add",
                    key="application.json",
                    format="json",
                    entries={"a": {"b": 1}},
                ),
            ],
        ),
    )

    assert json.loads(target["data"]["application.json"]) == {"a": {"b": 1}}
    assert changes[0]["status"] == "added"


def test_json_update_secret_is_base64_encoded() -> None:
    target = _secret({"creds.json": '{"user": "app", "password": "old"}'})

    _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(
                    action="update",
                    key="creds.json",
                    format="json",
                    entries={"password": "n3w"},
                ),
            ],
            kind="Secret",
        ),
    )

    assert json.loads(_decoded(target, "creds.json")) == {"user": "app", "password": "n3w"}


def test_json_delete_paths() -> None:
    target = _configmap({"application.json": '{"server": {"port": 1, "debug": true}}'})

    changes = _engine().apply(
        target,
        _definition(
            [
                UpdateOperation(
                    action="delete",
                    key="application.json",
                    format="json",
                    entries=["server.debug", "nope"],
                ),
            ],
        ),
    )

    assert json.loads(target["data"]["application.json"]) == {"server": {"port": 1}}
    assert [entry["status"] for entry in changes[0]["entries"]] == [
        "deleted",
        "unchanged_missing",
    ]


@pytest.mark.parametrize(
    "content, message",
    [
        ("{not json", "not valid JSON"),
        ("[1, 2]", "must contain an object"),
    ],
)
def test_json_invalid_existing_value_rejected(content: str, message: str) -> None:
    target = _configmap({"application.json": content})

    with pytest.raises(DeploymentUpdateTargetError, match=message):
        _engine().apply(
            target,
            _definition(
                [
                    UpdateOperation(
                        action="update",
                        key="application.json",
                        format="json",
                        entries={"a": 1},
                    ),
                ],
            ),
        )


# ----------------------------------------------------------------------
# Validator
# ----------------------------------------------------------------------


@pytest.mark.parametrize("operation_format", ["properties", "yaml", "json", "JSON"])
def test_validator_accepts_structured_formats(operation_format: str) -> None:
    operation = ConfigMapSecretUpdateValidator._operation(  # noqa: SLF001
        {
            "action": "update",
            "key": "application.data",
            "format": operation_format,
            "entries": {"a": "1"},
        },
    )

    assert operation.format == operation_format.lower()


def test_validator_rejects_unknown_format() -> None:
    with pytest.raises(UpdateDefinitionError, match="properties, yaml, json"):
        ConfigMapSecretUpdateValidator._operation(  # noqa: SLF001
            {
                "action": "update",
                "key": "application.data",
                "format": "toml",
                "entries": {"a": "1"},
            },
        )
