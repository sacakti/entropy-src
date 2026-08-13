from unittest.mock import Mock

import pytest

from lib.plugins.exceptions import PluginDisabledError
from lib.plugins.runner import PluginRunner


from lib.models.plugin import PluginResult


def test_runner_returns_plugin_result(execution_context):
    plugin = Mock()
    plugin.enabled = True

    plugin_class = Mock()

    result = PluginResult(
        success=True,
        changed=True,
        outputs={
            "image": "quay.io/example/app:1.0",
        },
    )

    instance = Mock()
    instance.execute.return_value = result
    plugin_class.return_value = instance

    loader = Mock()
    loader.get.return_value = plugin
    loader.load.return_value = plugin_class

    runner = PluginRunner(loader)

    actual = runner.execute(
        execution_context,
        "custom.docker_build",
    )

    assert actual is result
    assert actual.outputs["image"] == (
        "quay.io/example/app:1.0"
    )

    instance.execute.assert_called_once_with()


def test_runner_rejects_disabled_plugin(execution_context):
    plugin = Mock()
    plugin.enabled = False

    loader = Mock()
    loader.get.return_value = plugin

    runner = PluginRunner(loader)

    with pytest.raises(PluginDisabledError):
        runner.execute(
            execution_context,
            "custom.disabled",
        )

    loader.load.assert_not_called()
