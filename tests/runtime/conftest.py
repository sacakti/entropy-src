"""
Runtime test fixtures.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from core.context import EntropyContext
from core.runtime.context import ExecutionContext


@pytest.fixture
def entropy_context():

    context = Mock(spec=EntropyContext)

    #
    # Services
    #

    context.configuration = Mock()

    context.variable_manager = Mock()

    context.secret_manager = Mock()

    context.database_manager = Mock()

    context.template = Mock()

    context.executor = Mock()

    context.executor.mkdir = Mock()

    context.logger = Mock()

    context.observability = Mock()

    context.session_manager = Mock()

    context.paths = Mock()

    context.paths.logs = Mock()

    context.paths.logs.workflows = Path("/tmp/workflows")

    context.session_manager.require.return_value.username = "admin"

    return context


@pytest.fixture
def runtime(entropy_context):

    return ExecutionContext(
        entropy=entropy_context,
        workspace=Path("/tmp/runtime"),
    )
