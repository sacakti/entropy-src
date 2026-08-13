from pathlib import Path


def test_initial_runtime_state(runtime):
    assert runtime.variables == {}
    assert runtime.arguments == {}
    assert runtime.outputs == {}
    assert runtime.artifacts == {}
    assert runtime.workspace == runtime.workspace


def test_set_variables_replaces_previous_values(runtime):
    runtime.set_variables({"environment": "dev", "version": "1"})
    runtime.set_variables({"environment": "uat"})

    assert runtime.variables == {"environment": "uat"}


def test_set_arguments_replaces_previous_values(runtime):
    runtime.set_arguments({"source": "/a.zip", "replace": False})
    runtime.set_arguments({"source": "/b.zip"})

    assert runtime.arguments == {"source": "/b.zip"}


def test_start_loads_workflow_variables_and_clears_step_state(runtime):
    class Workflow:
        variables = {"environment": "uat"}

    runtime.arguments["stale"] = True
    runtime.outputs["stale"] = True
    runtime.artifacts["stale"] = Path("/tmp/stale")

    runtime.start(Workflow())

    assert runtime.variables == {"environment": "uat"}
    assert runtime.arguments == {}
    assert runtime.outputs == {}
    assert runtime.artifacts == {}
    assert runtime.execution.workflow is not None


def test_workspace_is_exposed(runtime):
    assert isinstance(runtime.workspace, Path)
