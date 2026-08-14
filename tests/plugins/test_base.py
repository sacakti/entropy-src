from lib.models.plugin import PluginResult


def test_plugin_exposes_context(plugin, plugin_context):
    assert plugin.context is plugin_context


def test_plugin_exposes_runtime_state(plugin, plugin_context):
    plugin_context._runtime.arguments["name"] = "entropy"
    plugin_context._runtime.variables["env"] = "uat"

    assert plugin.arguments.get("name") == "entropy"
    assert plugin.variables["env"] == "uat"
    assert plugin.outputs == {}
    assert plugin.artifacts == {}


def test_plugin_exposes_infrastructure(plugin):
    assert plugin.filesystem is not None
    assert plugin.shell is not None
    assert plugin.archive is not None
    assert plugin.environment is not None
    assert plugin.information is not None


def test_plugin_exposes_services(plugin):
    assert plugin.configuration is not None
    assert plugin.database is not None
    assert plugin.template is not None
    assert plugin.user == "tester"


def test_plugin_execute_returns_plugin_result(plugin) -> None:
    result = plugin.execute()

    assert isinstance(
        result,
        PluginResult,
    )

    assert result.success is True
    assert result.changed is True
    assert result.outputs["executed"] is True
