from unittest.mock import Mock

import pytest

from core.runtime.context import ExecutionContext
from lib.models.workflow import Workflow, WorkflowStep
from lib.workflow.runner import WorkflowRunner


@pytest.fixture
def entropy_context():
    context = Mock()

    context.observability = Mock()
    context.observability.emitter.return_value = Mock()

    context.ui = Mock()
    context.executor = Mock()
    context.configuration = Mock()
    context.database_manager = Mock()
    context.template = Mock()

    context.logging = Mock()
    context.logging.logger.return_value = Mock()

    context.session_manager = Mock()
    context.session_manager.require.return_value.username = "tester"

    return context


@pytest.fixture
def runtime(
    entropy_context,
    tmp_path,
):
    return ExecutionContext(
        entropy=entropy_context,
        workspace=tmp_path,
    )


@pytest.fixture
def workflow_runner():
    runner = object.__new__(
        WorkflowRunner,
    )

    runner._plugins = Mock()

    runner._context = Mock()
    runner._context.ui = Mock()

    return runner


@pytest.fixture
def workflow_step():
    return WorkflowStep(
        name="Build",
        plugin="custom.build",
        arguments={"source": "/release"},
        enabled=True,
        tags=["build"],
        on_failure="abort",
        suppress_result=False,
    )


@pytest.fixture
def workflow(
    workflow_step,
):
    return Workflow(
        name="Deploy",
        version="1.0",
        description="Deployment workflow",
        variables={
            "environment": "uat",
        },
        steps=[
            workflow_step,
        ],
    )
