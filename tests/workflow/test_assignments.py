import pytest

from lib.workflow.assignments import WorkflowAssignments
from lib.workflow.exceptions import WorkflowArgumentError


@pytest.fixture
def parser() -> WorkflowAssignments:
    return WorkflowAssignments()


def test_single_assignment(
    parser,
) -> None:

    assert parser.parse(
        ["environment=prod"],
    ) == {
        "environment": "prod",
    }


def test_multiple_assignments(
    parser,
) -> None:

    assert parser.parse(
        ["environment=prod;version=1.0.0"],
    ) == {
        "environment": "prod",
        "version": "1.0.0",
    }


def test_repeated_arguments(
    parser,
) -> None:

    assert parser.parse(
        [
            "environment=prod",
            "version=1.0.0",
        ],
    ) == {
        "environment": "prod",
        "version": "1.0.0",
    }


def test_custom_separator(
    parser,
) -> None:

    assert parser.parse(
        [
            'name="Aravinthan"&country="India"',
        ],
        separator="&",
    ) == {
        "name": "Aravinthan",
        "country": "India",
    }


def test_separator_inside_quotes(
    parser,
) -> None:

    assert parser.parse(
        [
            'message="hello;world";version=1.0.0',
        ],
    ) == {
        "message": "hello;world",
        "version": "1.0.0",
    }


def test_equals_inside_value(
    parser,
) -> None:

    assert parser.parse(
        [
            "url=https://example.com?a=1",
        ],
    ) == {
        "url": "https://example.com?a=1",
    }


def test_single_quotes_are_removed(
    parser,
) -> None:

    assert parser.parse(
        [
            "message='hello world'",
        ],
    ) == {
        "message": "hello world",
    }


def test_double_quotes_are_removed(
    parser,
) -> None:

    assert parser.parse(
        [
            'message="hello world"',
        ],
    ) == {
        "message": "hello world",
    }


def test_invalid_assignment(
    parser,
) -> None:

    with pytest.raises(
        WorkflowArgumentError,
        match="Expected KEY=VALUE",
    ):
        parser.parse(
            ["invalid"],
        )


def test_empty_key(
    parser,
) -> None:

    with pytest.raises(
        WorkflowArgumentError,
        match="must not be empty",
    ):
        parser.parse(
            ["=value"],
        )


def test_unterminated_quote(
    parser,
) -> None:

    with pytest.raises(
        WorkflowArgumentError,
        match="Unterminated quote",
    ):
        parser.parse(
            ['message="hello'],
        )

def test_parse_integer() -> None:
    parser = WorkflowAssignments()

    assert parser.parse_typed(
        ["retries=3"],
        value_type="integer",
    ) == {
        "retries": 3,
    }


def test_parse_boolean() -> None:
    parser = WorkflowAssignments()

    assert parser.parse_typed(
        ["enabled=true"],
        value_type="boolean",
    ) == {
        "enabled": True,
    }


def test_parse_list() -> None:
    parser = WorkflowAssignments()

    assert parser.parse_typed(
        ['args=["Pravin"]'],
        value_type="list",
    ) == {
        "args": ["Pravin"],
    }


def test_parse_dict() -> None:
    parser = WorkflowAssignments()

    assert parser.parse_typed(
        ['options={"name":"Pravin"}'],
        value_type="dict",
    ) == {
        "options": {
            "name": "Pravin",
        },
    }


def test_parse_json() -> None:
    parser = WorkflowAssignments()

    assert parser.parse_typed(
        ['value={"name":"Pravin","enabled":true}'],
        value_type="json",
    ) == {
        "value": {
            "name": "Pravin",
            "enabled": True,
        },
    }
