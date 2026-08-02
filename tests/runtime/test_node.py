from lib.models.runtime import ExecutionStatus
from lib.models.runtime import RuntimeNodeType
from core.runtime.node import RuntimeNode


def test_node_lifecycle():

    node = RuntimeNode(
        id="1",
        name="Validation",
        type=RuntimeNodeType.STAGE,
    )

    assert node.status is ExecutionStatus.CREATED

    node.start()

    assert node.running

    assert node.started_at is not None

    node.complete()

    assert node.succeeded

    assert node.duration_ms >= 0

    assert node.finished_at is not None

    assert node.duration_ms >= 0

def test_node_metadata():

    node = RuntimeNode(
        id="1",
        name="Validation",
        type=RuntimeNodeType.STAGE,
    )

    node.put("schema", "APP")

    assert node.get("schema") == "APP"

    node.update(
        file="master.sql",
        line=10,
    )

    assert node.get("file") == "master.sql"

    assert node.get("line") == 10

def test_node_hierarchy():

    root = RuntimeNode(
        id="1",
        name="Workflow",
        type=RuntimeNodeType.WORKFLOW,
    )

    child = RuntimeNode(
        id="2",
        name="Stage",
        type=RuntimeNodeType.STAGE,
    )

    root.add_child(child)

    assert child.parent is root

    assert child.depth == 1

    assert child.root is root
