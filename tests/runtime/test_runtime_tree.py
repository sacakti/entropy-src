from core.models.runtime import RuntimeNodeType


def test_enter_and_leave_nodes(runtime):
    node = runtime.enter(
        type=RuntimeNodeType.WORKFLOW,
        name="Deploy",
    )

    assert runtime.node is node

    runtime.leave()

    assert runtime.node is None


def test_step_scope_can_be_created(runtime):
    step = runtime.step(
        "Build",
        index=1,
        total=2,
    )

    assert step is not None
