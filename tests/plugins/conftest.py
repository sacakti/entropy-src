from pathlib import Path
from unittest.mock import Mock

import pytest

from core.runtime.context import ExecutionContext
from lib.plugins.base import BasePlugin
from lib.plugins.context import PluginContext
from lib.plugins.mode import PluginMode
from lib.models.plugin import PluginResult


class DummyPlugin(BasePlugin):

    def execute(self) -> PluginResult:

        return PluginResult(
            success=True,
            changed=True,
            outputs={
                "executed": True,
            },
        )

class FailingPlugin(BasePlugin):

    def execute(self) -> PluginResult:
        raise RuntimeError(
            "plugin failure",
        )

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
    context.session_manager = Mock()
    context.session_manager.require.return_value.username = "tester"

    context.logging = Mock()
    context.logging.logger.return_value = Mock()

    context.variables = {}
    context.arguments = {}
    context.outputs = {}
    context.artifacts = {}

    return context


@pytest.fixture
def execution_context(entropy_context, tmp_path):
    return ExecutionContext(
        entropy=entropy_context,
        workspace=tmp_path,
    )


@pytest.fixture
def plugin_context(execution_context):
    return PluginContext(
        context=execution_context,
        mode=PluginMode.WORKFLOW,
    )


@pytest.fixture
def plugin(plugin_context):
    return DummyPlugin(plugin_context)
