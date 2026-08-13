from lib.plugins.mode import PluginMode


def test_workflow_mode(plugin_context):
    assert plugin_context.mode is PluginMode.WORKFLOW
    assert plugin_context.automated is True
    assert plugin_context.interactive is False


def test_cli_mode(execution_context):
    from lib.plugins.context import PluginContext

    context = PluginContext(
        execution_context,
        PluginMode.CLI,
    )

    assert context.mode is PluginMode.CLI
    assert context.interactive is True
    assert context.automated is False


def test_arguments_are_typed_view(execution_context):
    execution_context.arguments = {
        "source": "/release.zip",
        "replace": True,
    }

    from lib.plugins.context import PluginContext

    context = PluginContext(
        execution_context,
        PluginMode.WORKFLOW,
    )

    assert context.arguments.get("source") == "/release.zip"
    assert context.arguments.get("replace") is True


def test_context_activity_delegates(execution_context):
    from lib.plugins.context import PluginContext

    execution_context.activity = lambda **kwargs: ("activity", kwargs)

    context = PluginContext(
        execution_context,
        PluginMode.WORKFLOW,
    )

    result = context.activity(
        "build",
        metadata={"image": "quay.io/example/app"},
    )

    assert result[0] == "activity"
    assert result[1]["name"] == "build"
    assert result[1]["metadata"]["image"] == "quay.io/example/app"
