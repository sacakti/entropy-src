from lib.models.workflow import Workflow, WorkflowStep


def test_workflow_defaults():
    workflow = Workflow(
        name="Deploy",
        version="1.0",
    )

    assert workflow.description is None
    assert workflow.variables == {}
    assert workflow.steps == []
    assert workflow.step_count == 0


def test_workflow_step_defaults():
    step = WorkflowStep(
        name="Build",
        plugin="custom.build",
    )

    assert step.arguments == {}
    assert step.enabled is True
    assert step.tags == []
    assert step.on_failure == "abort"
    assert step.suppress_result is False
    assert step.qualified_plugin == "custom.build"


def test_workflow_step_supports_result_suppression():
    step = WorkflowStep(
        name="Verbose step",
        plugin="custom.verbose",
        suppress_result=True,
    )

    assert step.suppress_result is True


def test_workflow_step_supports_continue_policy():
    step = WorkflowStep(
        name="Optional step",
        plugin="custom.optional",
        on_failure="continue",
    )

    assert step.on_failure == "continue"
