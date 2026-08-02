from lib.models.runtime import RuntimeNodeType
from core.runtime.node import RuntimeNode
from core.runtime.stack import RuntimeStack


def node(name):

    return RuntimeNode(
        id=name,
        name=name,
        type=RuntimeNodeType.STAGE,
    )


def test_push_pop():

    stack = RuntimeStack()

    a = node("a")

    b = node("b")

    stack.push(a)

    stack.push(b)

    assert stack.current() is b

    assert stack.parent() is a

    assert stack.depth() == 1

    assert stack.pop() is b

    assert stack.current() is a
