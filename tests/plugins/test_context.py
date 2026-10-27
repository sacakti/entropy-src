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



def test_data_directory_is_kept_per_plugin_and_project(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import lib.vault.projects as projects
    from lib.plugins.context import PluginContext

    monkeypatch.setattr(projects, "run_project", lambda: 7)

    def context(name):
        plugin_context = PluginContext.__new__(PluginContext)
        plugin_context._name = name
        plugin_context._runtime = SimpleNamespace(
            _entropy=SimpleNamespace(paths=SimpleNamespace(workspace=SimpleNamespace(root=tmp_path)))
        )
        return plugin_context

    folder = context("custom.demo").data_directory
    assert folder == tmp_path / "plugin-data" / "custom.demo" / "project-7"
    assert folder.is_dir()

    # A plugin run from a folder is named by the folder, inside plugin-data.
    local = context("/src/plugins/demo").data_directory
    assert local == tmp_path / "plugin-data" / "local.demo" / "project-7"
