def test_nested_execution(runtime):

    with runtime.stage(name="Validation"), runtime.activity(name="Parse SQL"):

        node = runtime.node

        assert node.name == "Parse SQL"

        assert node.depth == 1

    tree = runtime.tree

    root = tree.root

    assert root.name == "Validation"

    assert len(root.children) == 1

    assert root.children[0].name == "Parse SQL"
