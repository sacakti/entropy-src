from core.runtime.execution import WorkflowExecution


def test_execution_lifecycle(runtime):

    execution = WorkflowExecution(
        id="1",
        workflow=object(),
        context=runtime,
    )

    execution.start()

    assert execution.running

    execution.complete()

    assert execution.succeeded

    assert execution.finished
