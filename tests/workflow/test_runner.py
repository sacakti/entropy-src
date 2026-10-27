from unittest.mock import Mock

import pytest

from lib.models.plugin import PluginResult
from lib.workflow.runner import WorkflowRunner


@pytest.fixture
def workflow_runner(entropy_context):
    entropy_context.workflow_job_manager = Mock()

    plugin_runner = Mock()

    return WorkflowRunner(
        context=entropy_context,
        plugin_runner=plugin_runner,
    )


def test_step_output_is_passed_to_next_step(
    workflow_runner,
    runtime,
):
    first_result = PluginResult(
        success=True,
        outputs={
            "release_path": "/workspace/release",
        },
    )

    workflow_runner._plugins.execute.return_value = first_result

    first_step = Mock()
    first_step.name = "collect_release"
    first_step.plugin = "custom.release_collect"
    first_step.arguments = {}

    variable_resolver = Mock()
    variable_resolver.resolve.return_value = first_step.arguments

    workflow_runner._initialize(
        runtime,
        Mock(),
        first_step,
        variable_resolver,
    )

    workflow_runner._execute(
        runtime,
        Mock(),
        first_step,
    )

    second_step = Mock()
    second_step.name = "build_image"
    second_step.plugin = "custom.docker_build"
    second_step.arguments = {
        "source": ("${steps.collect_release.outputs.release_path}"),
    }

    variable_resolver = Mock()
    variable_resolver.resolve.return_value = second_step.arguments

    workflow_runner._initialize(
        runtime,
        Mock(),
        second_step,
        variable_resolver,
    )

    assert runtime.arguments["source"] == "/workspace/release"


def test_external_override_takes_precedence_over_step_output(
    workflow_runner,
    runtime,
):
    first_result = PluginResult(
        success=True,
        outputs={
            "release_path": "/workflow/release",
        },
    )

    runtime.set_step_result(
        "collect_release",
        first_result,
    )

    step = Mock()
    step.name = "build_image"
    step.plugin = "custom.docker_build"
    step.arguments = {
        "source": ("${steps.collect_release.outputs.release_path}"),
    }

    resolver = Mock()
    resolver.resolve.return_value = step.arguments

    workflow_runner._initialize(
        runtime,
        Mock(),
        step,
        resolver,
        overrides={
            "source": "/cli/release",
        },
    )

    assert runtime.arguments["source"] == "/cli/release"


def test_step_output_is_used_without_override(
    workflow_runner,
    runtime,
):
    runtime.set_step_result(
        "collect_release",
        PluginResult(
            success=True,
            outputs={
                "release_path": "/workflow/release",
            },
        ),
    )

    step = Mock()
    step.name = "build_image"
    step.plugin = "custom.docker_build"
    step.arguments = {
        "source": ("${steps.collect_release.outputs.release_path}"),
    }

    resolver = Mock()
    resolver.resolve.return_value = step.arguments

    workflow_runner._initialize(
        runtime,
        Mock(),
        step,
        resolver,
    )

    assert runtime.arguments["source"] == "/workflow/release"


def _failed_step(runtime, policy):
    step = Mock()
    step.name = "deploy"
    step.on_failure = policy
    runtime.set_step_result(
        "deploy",
        PluginResult(success=False, errors=[{"message": "host unreachable"}]),
    )
    return step


def test_unsuccessful_result_fails_the_step(workflow_runner, runtime):
    from lib.workflow.exceptions import StepFailedError

    step = _failed_step(runtime, "abort")
    with pytest.raises(StepFailedError, match="host unreachable"):
        workflow_runner._check_step_result(runtime, step)
    assert workflow_runner._recover(runtime, step, StepFailedError("x")) is False


def test_continue_policy_goes_on(workflow_runner, runtime):
    step = _failed_step(runtime, "continue")
    workflow_runner._context.ui = Mock()
    assert workflow_runner._recover(runtime, step, RuntimeError("boom")) is True


@pytest.mark.parametrize("answer, expected", [("resume", True), ("terminate", False)])
def test_pause_policy_waits_for_the_user(workflow_runner, runtime, monkeypatch, answer, expected):
    step = _failed_step(runtime, "pause")
    workflow_runner._context.ui = Mock()
    monkeypatch.setattr(workflow_runner, "_ask_resume", lambda *args: answer)
    assert workflow_runner._recover(runtime, step, RuntimeError("boom")) is expected


def test_pause_without_anyone_to_ask_terminates(workflow_runner, runtime, monkeypatch):
    monkeypatch.delenv("ENTROPY_RUN_MODE", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    step = _failed_step(runtime, "pause")
    workflow_runner._context.ui = Mock()
    assert workflow_runner._recover(runtime, step, RuntimeError("boom")) is False

