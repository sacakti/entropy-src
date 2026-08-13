from unittest.mock import Mock
from unittest.mock import patch
from lib.models.plugin import PluginResult


def test_execute_stores_plugin_result(
    workflow_runner,
    runtime,
):
    result = PluginResult(
        success=True,
        changed=True,
        outputs={
            "release_path": "/release/app",
        },
    )

    workflow_runner._plugins.execute.return_value = result

    step = Mock()
    step.name = "collect_release"
    step.plugin = "custom.release_collect"

    workflow_runner._execute(
        runtime,
        Mock(),
        step,
    )

    actual = runtime.get_step_result(
        "collect_release",
    )

    assert actual is result

    workflow_runner._plugins.execute.assert_called_once_with(
        context=runtime,
        qualified_name="custom.release_collect",
    )

def test_execute_stores_results_by_step_name(
    workflow_runner,
    runtime,
):
    first = PluginResult(
        outputs={
            "release_path": "/release/app",
        },
    )

    second = PluginResult(
        outputs={
            "image": "quay.io/example/app:1.0",
        },
    )

    workflow_runner._plugins.execute.side_effect = [
        first,
        second,
    ]

    first_step = Mock()
    first_step.name = "collect_release"
    first_step.plugin = "custom.release_collect"

    second_step = Mock()
    second_step.name = "build_image"
    second_step.plugin = "custom.docker_build"

    workflow_runner._execute(
        runtime,
        Mock(),
        first_step,
    )

    workflow_runner._execute(
        runtime,
        Mock(),
        second_step,
    )

    assert (
        runtime.get_step_result(
            "collect_release",
        )
        is first
    )

    assert (
        runtime.get_step_result(
            "build_image",
        )
        is second
    )

def test_report_result_prints_result(
    workflow_runner,
):
    result = PluginResult(
        success=True,
        changed=True,
        outputs={
            "image": "quay.io/example/app:1.0",
        },
    )

    step = Mock()
    step.name = "build_image"

    workflow_runner._report_result(
        step,
        result,
    )

    workflow_runner._context.ui.info.assert_called_once_with(
        "Result: build_image",
    )

    workflow_runner._context.ui.print.assert_called_once_with(
        result.to_dict(),
    )

def test_report_failed_result(
    workflow_runner,
):
    result = PluginResult(
        success=False,
        errors=[
            {
                "message": "Image build failed.",
            },
        ],
    )

    step = Mock()
    step.name = "build_image"

    workflow_runner._report_result(
        step,
        result,
    )

    workflow_runner._context.ui.error.assert_called_once_with(
        "Result: build_image failed.",
    )

    workflow_runner._context.ui.print.assert_called_once_with(
        result.to_dict(),
    )

def test_suppress_result_does_not_discard_result(
    workflow_runner,
    runtime,
):
    result = PluginResult(
        success=True,
        changed=True,
        outputs={
            "image": "quay.io/example/app:1.0",
        },
    )

    runtime.set_step_result(
        "build_image",
        result,
    )

    step = Mock()
    step.name = "build_image"
    step.suppress_result = True

    workflow_runner._report_step_result(
        runtime,
        step,
    )

    assert (
        runtime.get_step_result(
            "build_image",
        )
        is result
    )

    workflow_runner._report_result.assert_not_called()

def test_suppress_result_does_not_discard_result(
    workflow_runner,
    runtime,
):
    result = PluginResult(
        success=True,
        outputs={
            "image": "quay.io/example/app:1.0",
        },
    )

    runtime.set_step_result(
        "build_image",
        result,
    )

    step = Mock()
    step.name = "build_image"
    step.suppress_result = True

    with patch.object(
        workflow_runner,
        "_report_result",
    ) as report:
        workflow_runner._report_step_result(
            runtime,
            step,
        )

    report.assert_not_called()

    assert (
        runtime.get_step_result(
            "build_image",
        )
        is result
    )

def test_result_is_reported_when_not_suppressed(
    workflow_runner,
    runtime,
):
    result = PluginResult(
        success=True,
        outputs={
            "image": "quay.io/example/app:1.0",
        },
    )

    runtime.set_step_result(
        "build_image",
        result,
    )

    step = Mock()
    step.name = "build_image"
    step.suppress_result = False

    with patch.object(
        workflow_runner,
        "_report_result",
    ) as report:
        workflow_runner._report_step_result(
            runtime,
            step,
        )

    report.assert_called_once_with(
        step,
        result,
    )
