def test_context_services(runtime):

    assert runtime.configuration is not None

    assert runtime.variables is not None

    assert runtime.secrets is not None

    assert runtime.executor is not None


def test_context_tree(runtime):

    assert runtime.tree.root is None
