import pytest

from lib.workflow.exceptions import WorkflowArgumentError
from lib.workflow.overrides import WorkflowArgumentOverrides


@pytest.fixture
def overrides() -> WorkflowArgumentOverrides:
    return WorkflowArgumentOverrides()


def test_override_replaces_existing_argument(
    overrides,
) -> None:
    result = overrides.apply(
        {
            "source": "/workflow/release",
            "tag": "1.0.0",
        },
        {
            "source": "/cli/release",
        },
    )

    assert result == {
        "source": "/cli/release",
        "tag": "1.0.0",
    }


def test_multiple_overrides(
    overrides,
) -> None:
    result = overrides.apply(
        {
            "source": "/workflow/release",
            "repository": "quay.io/example/app",
            "tag": "1.0.0",
        },
        {
            "source": "/cli/release",
            "tag": "2.0.0",
        },
    )

    assert result == {
        "source": "/cli/release",
        "repository": "quay.io/example/app",
        "tag": "2.0.0",
    }


def test_no_overrides_returns_copy(
    overrides,
) -> None:
    arguments = {
        "source": "/release",
        "tag": "1.0.0",
    }

    result = overrides.apply(
        arguments,
        {},
    )

    assert result == arguments
    assert result is not arguments


def test_unknown_override_is_rejected(
    overrides,
) -> None:
    with pytest.raises(
        WorkflowArgumentError,
        match="Override argument 'repository'",
    ):
        overrides.apply(
            {
                "source": "/release",
            },
            {
                "repository": "quay.io/example/app",
            },
        )


def test_original_arguments_are_not_modified(
    overrides,
) -> None:
    arguments = {
        "source": "/workflow/release",
        "tag": "1.0.0",
    }

    overrides.apply(
        arguments,
        {
            "source": "/cli/release",
        },
    )

    assert arguments == {
        "source": "/workflow/release",
        "tag": "1.0.0",
    }
