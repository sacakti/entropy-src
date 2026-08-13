from pathlib import Path


def test_outputs_are_mutable_runtime_state(runtime):
    runtime.outputs["release"] = {
        "path": "/release/app.zip",
    }

    assert runtime.outputs["release"]["path"] == "/release/app.zip"


def test_artifacts_are_path_values(runtime):
    artifact = Path("/workspace/app.tar")

    runtime.artifacts["image"] = artifact

    assert runtime.artifacts["image"] == artifact


def test_runtime_state_is_independent_between_context_instances(
    entropy_context,
    tmp_path,
):
    from core.runtime.context import ExecutionContext

    first = ExecutionContext(
        entropy=entropy_context,
        workspace=tmp_path / "one",
    )
    second = ExecutionContext(
        entropy=entropy_context,
        workspace=tmp_path / "two",
    )

    first.outputs["x"] = 1

    assert second.outputs == {}
