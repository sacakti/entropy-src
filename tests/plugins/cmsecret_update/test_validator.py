from __future__ import annotations

import pytest
from cm_secret_update.exceptions import (
    UpdateDefinitionError,
)
from cm_secret_update.model import (
    ConfigMapSecretUpdate,
    UpdateOperation,
    UpdateTarget,
)
from cm_secret_update.validator import (
    ConfigMapSecretUpdateValidator,
)


def _definition(
    **overrides,
) -> dict:
    value = {
        "apiVersion": "entropy/v1",
        "kind": "ConfigMapSecretUpdate",
        "target": {
            "kind": "ConfigMap",
            "name": "application-config",
        },
        "operations": [
            {
                "action": "update",
                "key": "environment",
                "value": "uat",
            },
        ],
    }

    value.update(overrides)

    return value


def test_parse_valid_definition() -> None:
    result = ConfigMapSecretUpdateValidator.parse(
        _definition(),
    )

    assert isinstance(
        result,
        ConfigMapSecretUpdate,
    )

    assert result.api_version == "entropy/v1"
    assert result.kind == "ConfigMapSecretUpdate"

    assert result.target == UpdateTarget(
        kind="ConfigMap",
        name="application-config",
    )

    assert result.operations == [
        UpdateOperation(
            action="update",
            key="environment",
            value="uat",
            format=None,
            entries=None,
        ),
    ]


def test_parse_secret_target() -> None:
    definition = _definition(
        target={
            "kind": "Secret",
            "name": "application-secret",
        },
    )

    result = ConfigMapSecretUpdateValidator.parse(
        definition,
    )

    assert result.target.kind == "Secret"
    assert result.target.name == "application-secret"


def test_parse_multiple_operations() -> None:
    definition = _definition(
        operations=[
            {
                "action": "add",
                "key": "new.setting",
                "value": "enabled",
            },
            {
                "action": "update",
                "key": "environment",
                "value": "uat",
            },
            {
                "action": "delete",
                "key": "old.setting",
            },
        ],
    )

    result = ConfigMapSecretUpdateValidator.parse(
        definition,
    )

    assert len(result.operations) == 3

    assert result.operations[0].action == "add"
    assert result.operations[1].action == "update"
    assert result.operations[2].action == "delete"


def test_action_is_normalized() -> None:
    definition = _definition(
        operations=[
            {
                "action": "  UPDATE  ",
                "key": "environment",
                "value": "uat",
            },
        ],
    )

    result = ConfigMapSecretUpdateValidator.parse(
        definition,
    )

    assert result.operations[0].action == "update"


def test_key_is_trimmed() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "key": "  environment  ",
                "value": "uat",
            },
        ],
    )

    result = ConfigMapSecretUpdateValidator.parse(
        definition,
    )

    assert result.operations[0].key == "environment"


def test_format_is_normalized() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "key": "application.properties",
                "format": "  PROPERTIES  ",
                "entries": {
                    "application.name": "entropy",
                },
            },
        ],
    )

    result = ConfigMapSecretUpdateValidator.parse(
        definition,
    )

    assert result.operations[0].format == "properties"


def test_yaml_format_is_supported() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "key": "redis.yaml",
                "format": "yaml",
                "entries": {
                    "nettyThreads": 64,
                },
            },
        ],
    )

    result = ConfigMapSecretUpdateValidator.parse(
        definition,
    )

    operation = result.operations[0]

    assert operation.format == "yaml"
    assert operation.entries == {
        "nettyThreads": 64,
    }
    assert operation.value is None


def test_non_object_definition_rejected() -> None:
    with pytest.raises(
        UpdateDefinitionError,
        match="must be an object",
    ):
        ConfigMapSecretUpdateValidator.parse(
            [],
        )


def test_invalid_api_version_rejected() -> None:
    definition = _definition(
        apiVersion="v1",
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Unsupported apiVersion",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_invalid_kind_rejected() -> None:
    definition = _definition(
        kind="ConfigMap",
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Invalid update definition kind",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_missing_target_rejected() -> None:
    definition = _definition(
        target=None,
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="'target' must be an object",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_invalid_target_kind_rejected() -> None:
    definition = _definition(
        target={
            "kind": "Deployment",
            "name": "application",
        },
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Unsupported target kind",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_missing_target_name_rejected() -> None:
    definition = _definition(
        target={
            "kind": "ConfigMap",
        },
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Target 'name' must be a non-empty string",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_empty_target_name_rejected() -> None:
    definition = _definition(
        target={
            "kind": "ConfigMap",
            "name": "   ",
        },
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Target 'name' must be a non-empty string",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_operations_must_be_list() -> None:
    definition = _definition(
        operations={},
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="'operations' must be an array",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_operations_cannot_be_empty() -> None:
    definition = _definition(
        operations=[],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="'operations' cannot be empty",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_operation_must_be_object() -> None:
    definition = _definition(
        operations=[
            "invalid",
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Each operation must be an object",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_action_must_be_string() -> None:
    definition = _definition(
        operations=[
            {
                "action": 123,
                "key": "environment",
                "value": "uat",
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Operation 'action' must be a string",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


@pytest.mark.parametrize(
    "action",
    [
        "replace",
        "create",
        "remove",
        "",
    ],
)
def test_unsupported_action_rejected(
    action: str,
) -> None:
    definition = _definition(
        operations=[
            {
                "action": action,
                "key": "environment",
                "value": "uat",
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Unsupported operation",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_missing_key_rejected() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "value": "uat",
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Operation 'key' must be a non-empty string",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_empty_key_rejected() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "key": "   ",
                "value": "uat",
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Operation 'key' must be a non-empty string",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_format_must_be_string() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "key": "application.properties",
                "format": 123,
                "entries": {},
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="must be a string",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_unsupported_format_rejected() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "key": "application.properties",
                "format": "json",
                "entries": {},
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="Unsupported format",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_entries_must_be_object() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "key": "application.properties",
                "format": "properties",
                "entries": [],
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="'entries'.*must be an object",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_delete_cannot_have_format() -> None:
    definition = _definition(
        operations=[
            {
                "action": "delete",
                "key": "environment",
                "format": "properties",
                "entries": {},
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="cannot specify 'format'",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_delete_cannot_have_entries() -> None:
    definition = _definition(
        operations=[
            {
                "action": "delete",
                "key": "environment",
                "entries": {},
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="cannot specify 'entries'",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_delete_cannot_have_value() -> None:
    definition = _definition(
        operations=[
            {
                "action": "delete",
                "key": "environment",
                "value": "uat",
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="cannot specify 'value'",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


@pytest.mark.parametrize(
    "action",
    [
        "add",
        "update",
    ],
)
def test_scalar_operation_requires_value(
    action: str,
) -> None:
    definition = _definition(
        operations=[
            {
                "action": action,
                "key": "environment",
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="requires 'value'",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


@pytest.mark.parametrize(
    "action",
    [
        "add",
        "update",
    ],
)
def test_scalar_operation_cannot_have_entries(
    action: str,
) -> None:
    definition = _definition(
        operations=[
            {
                "action": action,
                "key": "environment",
                "value": "uat",
                "entries": {},
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="cannot specify 'entries'",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


@pytest.mark.parametrize(
    "action",
    [
        "add",
        "update",
    ],
)
@pytest.mark.parametrize(
    "operation_format",
    [
        "properties",
        "yaml",
    ],
)
def test_structured_operation_requires_entries(
    action: str,
    operation_format: str,
) -> None:
    definition = _definition(
        operations=[
            {
                "action": action,
                "key": "application.properties",
                "format": operation_format,
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="requires 'entries'",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


@pytest.mark.parametrize(
    "action",
    [
        "add",
        "update",
    ],
)
@pytest.mark.parametrize(
    "operation_format",
    [
        "properties",
        "yaml",
    ],
)
def test_structured_operation_cannot_have_value(
    action: str,
    operation_format: str,
) -> None:
    definition = _definition(
        operations=[
            {
                "action": action,
                "key": "application.properties",
                "format": operation_format,
                "entries": {
                    "application.name": "entropy",
                },
                "value": "invalid",
            },
        ],
    )

    with pytest.raises(
        UpdateDefinitionError,
        match="cannot specify 'value'",
    ):
        ConfigMapSecretUpdateValidator.parse(
            definition,
        )


def test_delete_operation_has_no_value_or_entries() -> None:
    definition = _definition(
        operations=[
            {
                "action": "delete",
                "key": "old_password",
            },
        ],
    )

    result = ConfigMapSecretUpdateValidator.parse(
        definition,
    )

    operation = result.operations[0]

    assert operation.action == "delete"
    assert operation.key == "old_password"
    assert operation.value is None
    assert operation.format is None
    assert operation.entries is None


def test_scalar_value_can_be_non_string() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "key": "port",
                "value": 8081,
            },
        ],
    )

    result = ConfigMapSecretUpdateValidator.parse(
        definition,
    )

    assert result.operations[0].value == 8081


def test_structured_entries_can_contain_nested_values() -> None:
    definition = _definition(
        operations=[
            {
                "action": "update",
                "key": "redis.yaml",
                "format": "yaml",
                "entries": {
                    "nettyThreads": 64,
                    "singleServerConfig": {
                        "timeout": 1500,
                    },
                },
            },
        ],
    )

    result = ConfigMapSecretUpdateValidator.parse(
        definition,
    )

    assert result.operations[0].entries == {
        "nettyThreads": 64,
        "singleServerConfig": {
            "timeout": 1500,
        },
    }
