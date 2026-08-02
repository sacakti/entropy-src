from lib.models.workflow import FailurePolicy, WorkflowPolicy


def test_defaults():

    policy = WorkflowPolicy()

    assert policy.enabled is True
    assert policy.retries == 0
    assert policy.on_failure is FailurePolicy.ABORT
    assert policy.timeout is None


def test_custom():

    policy = WorkflowPolicy(
        enabled=False,
        retries=5,
        timeout=100,
        on_failure=FailurePolicy.CONTINUE,
    )

    assert policy.enabled is False
    assert policy.retries == 5
    assert policy.timeout == 100
    assert policy.on_failure is FailurePolicy.CONTINUE


def test_step(workflow_step):

    assert workflow_step.id == "step1"

    assert workflow_step.order == 1

    assert workflow_step.plugin == "validate"

    assert workflow_step.configuration["directory"] == "scripts"


def test_iteration(workflow):

    assert len(workflow) == 1

    assert workflow[0].name == "Validate"

    assert list(workflow)[0].plugin == "validate"
