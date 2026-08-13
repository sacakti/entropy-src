from lib.models.plugin import PluginResult
from lib.workflow.arguments import WorkflowArgumentResolver
from lib.workflow.exceptions import WorkflowArgumentError


def test_resolves_nested_step_output() -> None:
    resolver = WorkflowArgumentResolver()

    result = PluginResult(
        outputs={
            "release": {
                "destination": "/workspace/release",
            },
        },
    )

    arguments = resolver.resolve(
        {
            "destination": (
                "${steps.collect_release.outputs.release.destination}"
            ),
        },
        variables={},
        step_results={
            "collect_release": result,
        },
    )

    assert arguments == {
        "destination": "/workspace/release",
    }


def test_resolves_list_output_without_string_conversion() -> None:
    resolver = WorkflowArgumentResolver()

    services = [
        {
            "name": "app1",
            "path": "/release/app1",
        },
        {
            "name": "app2",
            "path": "/release/app2",
        },
    ]

    result = PluginResult(
        outputs={
            "services": services,
        },
    )

    arguments = resolver.resolve(
        {
            "services": "${steps.collect_release.outputs.services}",
        },
        variables={},
        step_results={
            "collect_release": result,
        },
    )

    assert arguments["services"] == services
    assert isinstance(
        arguments["services"],
        list,
    )


def test_resolves_nested_values_inside_list() -> None:
    resolver = WorkflowArgumentResolver()

    result = PluginResult(
        outputs={
            "services": [
                {
                    "name": "app1",
                    "path": "/release/app1",
                },
                {
                    "name": "app2",
                    "path": "/release/app2",
                },
            ],
        },
    )

    arguments = resolver.resolve(
        {
            "services": [
                "${steps.collect_release.outputs.services}"
            ],
        },
        variables={},
        step_results={
            "collect_release": result,
        },
    )

    assert arguments["services"] == [result.outputs["services"]]


def test_resolves_multiple_outputs_from_same_step() -> None:
    resolver = WorkflowArgumentResolver()

    result = PluginResult(
        outputs={
            "release_path": "/workspace/release",
            "release_name": "my-release.zip",
            "version": "1.4.2",
        },
    )

    arguments = resolver.resolve(
        {
            "source": "${steps.collect.outputs.release_path}",
            "package": "${steps.collect.outputs.release_name}",
            "version": "${steps.collect.outputs.version}",
        },
        variables={},
        step_results={
            "collect": result,
        },
    )

    assert arguments == {
        "source": "/workspace/release",
        "package": "my-release.zip",
        "version": "1.4.2",
    }


def test_missing_step_result_raises_error() -> None:
    resolver = WorkflowArgumentResolver()

    try:
        resolver.resolve(
            {
                "source": "${steps.collect.outputs.release_path}",
            },
            variables={},
            step_results={},
        )
    except WorkflowArgumentError as exc:
        assert "collect" in str(exc)
    else:
        raise AssertionError(
            "Expected WorkflowArgumentError.",
        )


def test_missing_step_output_raises_error() -> None:
    resolver = WorkflowArgumentResolver()

    result = PluginResult(
        outputs={
            "release_path": "/workspace/release",
        },
    )

    try:
        resolver.resolve(
            {
                "source": "${steps.collect.outputs.missing}",
            },
            variables={},
            step_results={
                "collect": result,
            },
        )
    except WorkflowArgumentError as exc:
        assert "steps.collect.outputs.missing" in str(exc)
    else:
        raise AssertionError(
            "Expected WorkflowArgumentError.",
        )


def test_invalid_step_reference_raises_error() -> None:
    resolver = WorkflowArgumentResolver()

    try:
        resolver.resolve(
            {
                "source": "${steps.collect.release_path}",
            },
            variables={},
            step_results={},
        )
    except WorkflowArgumentError as exc:
        assert "Invalid step output reference" in str(exc)
    else:
        raise AssertionError(
            "Expected WorkflowArgumentError.",
        )
