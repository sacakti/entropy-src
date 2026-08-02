from unittest.mock import Mock

from lib.workflow.manager import WorkflowManager


def test_manager_load(
    entropy_context,
    workflow_document,
):

    entropy_context.executor.read_document.return_value = workflow_document

    manager = WorkflowManager(
        entropy_context,
    )

    workflow = manager.load(
        Mock(),
    )

    assert workflow.name == "Deploy"

    entropy_context.executor.read_document.assert_called_once()
