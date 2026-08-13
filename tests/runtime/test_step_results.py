from lib.models.plugin import PluginResult


def test_execution_context_starts_with_empty_step_results(
    runtime,
) -> None:
    assert runtime.step_results == {}


def test_set_step_result_stores_result(
    runtime,
) -> None:
    result = PluginResult(
        success=True,
        changed=True,
        outputs={
            "release_path": "/release/app",
        },
    )

    runtime.set_step_result(
        "collect_release",
        result,
    )

    assert (
        runtime.step_results["collect_release"]
        is result
    )


def test_get_step_result_returns_result(
    runtime,
) -> None:
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

    actual = runtime.get_step_result(
        "build_image",
    )

    assert actual is result


def test_get_missing_step_result_returns_none(
    runtime,
) -> None:
    assert (
        runtime.get_step_result(
            "missing",
        )
        is None
    )


def test_step_results_are_replaced_for_same_step(
    runtime,
) -> None:
    first = PluginResult(
        outputs={
            "value": "first",
        },
    )

    second = PluginResult(
        outputs={
            "value": "second",
        },
    )

    runtime.set_step_result(
        "step",
        first,
    )

    runtime.set_step_result(
        "step",
        second,
    )

    assert (
        runtime.get_step_result(
            "step",
        )
        is second
    )


def test_start_clears_previous_step_results(
    runtime,
) -> None:
    result = PluginResult(
        outputs={
            "value": "old",
        },
    )

    runtime.set_step_result(
        "old_step",
        result,
    )

    assert runtime.step_results

    class Workflow:
        variables = {}

    runtime.start(
        Workflow(),
    )

    assert runtime.step_results == {}
