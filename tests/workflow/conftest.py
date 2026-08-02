from unittest.mock import Mock

import pytest

from lib.models.workflow import FailurePolicy, WorkflowDefinition, WorkflowPolicy, WorkflowStep


@pytest.fixture
def workflow_document():

    return {
        "name": "Deploy",
        "version": "1.0",
        "description": "Sample workflow",
        "steps": [
            {
                "id": "step1",
                "order": 1,
                "name": "Validate",
                "plugin": "validate",
                "enabled": True,
                "retry_count": 3,
                "on_failure": "abort",
                "config": {
                    "directory": "scripts",
                },
            }
        ],
    }


@pytest.fixture
def workflow_policy():

    return WorkflowPolicy(
        enabled=True,
        retries=3,
        on_failure=FailurePolicy.ABORT,
    )


@pytest.fixture
def workflow_step(workflow_policy):

    return WorkflowStep(
        id="step1",
        order=1,
        name="Validate",
        plugin="validate",
        configuration={
            "directory": "scripts",
        },
        policy=workflow_policy,
    )


@pytest.fixture
def workflow(workflow_step):

    return WorkflowDefinition(
        name="Deploy",
        version="1.0",
        description="Sample",
        steps=[workflow_step],
    )


@pytest.fixture
def entropy_context():

    context = Mock()

    context.executor = Mock()

    context.execution_manager = Mock()

    context.plugin_manager = Mock()

    return context
