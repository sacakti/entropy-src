from lib.models.runtime import RuntimeNodeType

from core.runtime.tree import RuntimeTree


def test_tree_enter_leave():

    tree = RuntimeTree()

    workflow = tree.enter(
        type=RuntimeNodeType.WORKFLOW,
        name="Deploy",
    )

    stage = tree.enter(
        type=RuntimeNodeType.STAGE,
        name="Validation",
    )

    assert stage.parent is workflow

    assert tree.current is stage

    tree.leave()

    assert tree.current is workflow


def test_tree_walk():

    tree = RuntimeTree()

    tree.enter(
        type=RuntimeNodeType.WORKFLOW,
        name="Workflow",
    )

    tree.enter(
        type=RuntimeNodeType.STAGE,
        name="Stage",
    )

    names = [n.name for n in tree.walk()]

    assert names == [
        "Workflow",
        "Stage",
    ]
