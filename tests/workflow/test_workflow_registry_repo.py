"""
Workflow registry repository tests.
"""

from datetime import datetime, timezone

import pytest

from lib.database.repositories.workflow_registry import (
    WorkflowRegistryRepository,
)
from lib.models.workflow_registry import WorkflowRegistryEntry


def create_entry(
    name: str = "test",
) -> WorkflowRegistryEntry:

    now = datetime.now(
        timezone.utc,
    )

    return WorkflowRegistryEntry(
        id=None,
        name=name,
        version="1.0.0",
        description="Test workflow.",
        definition='{"name":"test"}',
        created_at=now,
        updated_at=now,
    )


def test_add(repository: WorkflowRegistryRepository) -> None:

    entry = repository.add(
        create_entry(),
    )

    assert entry.id is not None
    assert entry.name == "test"
    assert entry.version == "1.0.0"


def test_get(repository: WorkflowRegistryRepository) -> None:

    repository.add(
        create_entry(),
    )

    entry = repository.get(
        "test",
    )

    assert entry.name == "test"
    assert entry.definition == '{"name":"test"}'


def test_exists(repository: WorkflowRegistryRepository) -> None:

    assert not repository.exists(
        "test",
    )

    repository.add(
        create_entry(),
    )

    assert repository.exists(
        "test",
    )


def test_list(repository: WorkflowRegistryRepository) -> None:

    repository.add(
        create_entry("workflow-a"),
    )

    repository.add(
        create_entry("workflow-b"),
    )

    workflows = repository.list()

    assert len(workflows) == 2

    assert [
        workflow.name
        for workflow in workflows
    ] == [
        "workflow-a",
        "workflow-b",
    ]


def test_replace(
    repository: WorkflowRegistryRepository,
) -> None:

    repository.add(
        create_entry(),
    )

    now = datetime.now(
        timezone.utc,
    )

    replacement = WorkflowRegistryEntry(
        id=None,
        name="test",
        version="2.0.0",
        description="Updated workflow.",
        definition='{"name":"test","version":"2.0.0"}',
        created_at=now,
        updated_at=now,
    )

    result = repository.replace(
        "test",
        replacement,
    )

    assert result.name == "test"
    assert result.version == "2.0.0"
    assert result.description == "Updated workflow."
    assert result.definition == (
        '{"name":"test","version":"2.0.0"}'
    )


def test_remove(
    repository: WorkflowRegistryRepository,
) -> None:

    repository.add(
        create_entry(),
    )

    repository.remove(
        "test",
    )

    assert not repository.exists(
        "test",
    )


def test_duplicate(
    repository: WorkflowRegistryRepository,
) -> None:

    repository.add(
        create_entry(),
    )

    with pytest.raises(Exception):

        repository.add(
            create_entry(),
        )


def test_missing_get(
    repository: WorkflowRegistryRepository,
) -> None:

    with pytest.raises(
        KeyError,
    ):

        repository.get(
            "missing",
        )


def test_missing_replace(
    repository: WorkflowRegistryRepository,
) -> None:

    with pytest.raises(
        KeyError,
    ):

        repository.replace(
            "missing",
            create_entry(
                "missing",
            ),
        )


def test_missing_remove(
    repository: WorkflowRegistryRepository,
) -> None:

    with pytest.raises(
        KeyError,
    ):

        repository.remove(
            "missing",
        )
