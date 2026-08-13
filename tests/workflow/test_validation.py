from unittest.mock import Mock

import pytest

from lib.models.workflow import Workflow, WorkflowStep
from lib.workflow.exceptions import InvalidWorkflowError
from lib.workflow.validator import WorkflowValidator


@pytest.fixture
def plugin_manager():
    manager = Mock()
    manager.exists.return_value = True
    return manager


@pytest.fixture
def validator(plugin_manager):
    return WorkflowValidator(
        plugin_manager,
    )


def test_validator_accepts_valid_workflow(
    validator,
    workflow,
):
    result = validator.validate(
        workflow,
    )

    assert result is None


def test_validator_rejects_duplicate_step_names(
    validator,
):
    workflow = Workflow(
        name="Deploy",
        version="1.0",
        steps=[
            WorkflowStep(
                name="Build",
                plugin="custom.build",
            ),
            WorkflowStep(
                name="Build",
                plugin="custom.test",
            ),
        ],
    )

    with pytest.raises(
        InvalidWorkflowError,
        match="Duplicate step 'Build'",
    ):
        validator.validate(
            workflow,
        )


def test_validator_rejects_missing_plugin(
    plugin_manager,
):
    plugin_manager.exists.return_value = False

    validator = WorkflowValidator(
        plugin_manager,
    )

    workflow = Workflow(
        name="Deploy",
        version="1.0",
        steps=[
            WorkflowStep(
                name="Build",
                plugin="custom.build",
            ),
        ],
    )

    with pytest.raises(
        InvalidWorkflowError,
        match="Plugin 'custom.build' is not installed",
    ):
        validator.validate(
            workflow,
        )


def test_validator_rejects_missing_workflow_name(
    validator,
):
    workflow = Workflow(
        name="",
        version="1.0",
        steps=[
            WorkflowStep(
                name="Build",
                plugin="custom.build",
            ),
        ],
    )

    with pytest.raises(
        InvalidWorkflowError,
        match="Workflow name is required",
    ):
        validator.validate(
            workflow,
        )


def test_validator_rejects_empty_workflow(
    validator,
):
    workflow = Workflow(
        name="Deploy",
        version="1.0",
        steps=[],
    )

    with pytest.raises(
        InvalidWorkflowError,
        match="Workflow contains no steps",
    ):
        validator.validate(
            workflow,
        )


def test_validator_rejects_missing_step_name(
    validator,
):
    workflow = Workflow(
        name="Deploy",
        version="1.0",
        steps=[
            WorkflowStep(
                name="",
                plugin="custom.build",
            ),
        ],
    )

    with pytest.raises(
        InvalidWorkflowError,
        match="Workflow step name is required",
    ):
        validator.validate(
            workflow,
        )


def test_validator_rejects_missing_step_plugin(
    validator,
):
    workflow = Workflow(
        name="Deploy",
        version="1.0",
        steps=[
            WorkflowStep(
                name="Build",
                plugin="",
            ),
        ],
    )

    with pytest.raises(
        InvalidWorkflowError,
        match="Step 'Build' has no plugin",
    ):
        validator.validate(
            workflow,
        )
