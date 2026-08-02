from unittest.mock import MagicMock, Mock

import pytest

from lib.workflow.exceptions import WorkflowExecutionError
from lib.workflow.execution import WorkflowExecutor


def test_execute(
    entropy_context,
    workflow,
):

    execution = Mock()

    execution.context = Mock()
    execution.context.stage.return_value = MagicMock()

    entropy_context.execution_manager.start.return_value = execution

    plugin = Mock()

    entropy_context.plugin_manager.load.return_value = plugin

    WorkflowExecutor(
        entropy_context,
    ).execute(
        workflow,
    )

    entropy_context.execution_manager.start.assert_called_once_with(
        workflow,
    )

    entropy_context.plugin_manager.load.assert_called_once_with(
        "validate",
    )

    plugin.run.assert_called_once()

    execution.complete.assert_called_once()

    execution.fail.assert_not_called()


def test_failed_execution(
    entropy_context,
    workflow,
):

    execution = Mock()

    execution.context = Mock()
    execution.context.stage.return_value = MagicMock()

    entropy_context.execution_manager.start.return_value = execution

    plugin = Mock()
    plugin.run.side_effect = RuntimeError()

    entropy_context.plugin_manager.load.return_value = plugin

    # with pytest.raises(RuntimeError):

    with pytest.raises(WorkflowExecutionError):

        WorkflowExecutor(
            entropy_context,
        ).execute(
            workflow,
        )

    execution.fail.assert_called_once()

    execution.complete.assert_not_called()
