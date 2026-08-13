from pathlib import Path
from unittest.mock import Mock

import pytest

from core.runtime.context import ExecutionContext


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
def runtime(entropy_context, tmp_path):
    return ExecutionContext(
        entropy=entropy_context,
        workspace=tmp_path,
    )
