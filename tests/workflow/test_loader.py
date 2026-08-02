from lib.workflow.loader import WorkflowLoader


def test_load(workflow_document):

    loader = WorkflowLoader()

    workflow = loader.load(
        workflow_document,
    )

    assert workflow.name == "Deploy"

    assert len(workflow.steps) == 1

    step = workflow.steps[0]

    assert step.id == "step1"

    assert step.policy.retries == 3
