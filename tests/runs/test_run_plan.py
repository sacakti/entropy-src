"""Run plans: step selection, tag filters, node segments and output hand-over."""

import pytest

from lib.models.workflow import Workflow, WorkflowStep
from lib.runs.plan import PlanError, build_plan, segment_workflow, step_references


def _workflow() -> Workflow:
    return Workflow(
        name="deploy",
        version="1.0.0",
        steps=[
            WorkflowStep(name="build", plugin="builtin.shell", tags=["ci"]),
            WorkflowStep(
                name="test",
                plugin="builtin.shell",
                tags=["ci", "slow"],
                arguments={"artifact": "${steps.build.outputs.path}"},
            ),
            WorkflowStep(name="docs", plugin="builtin.hello", enabled=False),
            WorkflowStep(
                name="ship",
                plugin="builtin.shell",
                tags=["deploy"],
                arguments={
                    "files": ["${steps.build.outputs.path}", "README"],
                    "meta": {"report": "${steps.test.outputs.report.url}"},
                },
            ),
        ],
    )


def test_default_plan_runs_enabled_steps_on_one_node() -> None:
    plan = build_plan(_workflow())

    assert plan.selected == ["build", "test", "ship"]
    assert plan.skipped == ["docs"]
    assert plan.trivial
    assert plan.segments == [{"node": "local", "steps": ["build", "test", "ship"]}]
    assert plan.steps[2]["skip_reason"] == "disabled"


def test_references_are_found_in_nested_arguments() -> None:
    step = _workflow().steps[3]
    assert step_references(step.arguments) == [("build", "path"), ("test", "report.url")]


def test_tag_filter_and_explicit_selection() -> None:
    plan = build_plan(_workflow(), tags=["ci"])
    assert plan.selected == ["build", "test"]
    assert plan.steps[3]["skip_reason"] == "tag filter"
    assert not plan.trivial

    plan = build_plan(_workflow(), steps=["build"])
    assert plan.selected == ["build"]


def test_selecting_a_step_without_its_inputs_is_refused() -> None:
    with pytest.raises(PlanError, match="uses the output of step 'build'"):
        build_plan(_workflow(), steps=["test"])

    with pytest.raises(PlanError, match="No steps"):
        build_plan(_workflow(), tags=["nothing"])

    with pytest.raises(PlanError, match="Unknown step"):
        build_plan(_workflow(), step_nodes={"nope": "edge-1"})


def test_step_nodes_split_the_run_into_ordered_segments() -> None:
    plan = build_plan(_workflow(), step_nodes={"test": "edge-1"})

    assert plan.segments == [
        {"node": "local", "steps": ["build"]},
        {"node": "edge-1", "steps": ["test"]},
        {"node": "local", "steps": ["ship"]},
    ]
    assert plan.nodes == ["local", "edge-1"]
    snapshot = plan.snapshot({"secret": "x"})
    assert snapshot["variables"] == ["secret"]
    assert "x" not in str(snapshot)


def test_segments_receive_outputs_of_earlier_segments() -> None:
    outputs = {"build": {"path": "/tmp/app.tar"}, "test": {"report": {"url": "http://r"}}}

    segment = segment_workflow(_workflow(), ["ship"], outputs)

    assert [step.name for step in segment.steps] == ["ship"]
    assert segment.steps[0].arguments == {
        "files": ["/tmp/app.tar", "README"],
        "meta": {"report": "http://r"},
    }

    # References inside the same segment stay for the engine to resolve.
    together = segment_workflow(_workflow(), ["build", "test"], {})
    assert together.steps[1].arguments == {"artifact": "${steps.build.outputs.path}"}


def test_missing_outputs_are_reported() -> None:
    with pytest.raises(PlanError, match="no output 'path'"):
        segment_workflow(_workflow(), ["test"], {"build": {}})
