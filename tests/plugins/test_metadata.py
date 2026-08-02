from lib.plugins.metadata import PluginMetadata


def test_metadata_defaults():

    metadata = PluginMetadata(
        name="git",
        namespace="source",
        version="1.0",
        package="plugins.source.git",
        module="plugins.source.git.plugin",
    )

    assert metadata.display_name is None
    assert metadata.description is None
    assert metadata.author is None
    assert metadata.tags == ()


def test_qualified_name(metadata):

    assert metadata.qualified_name == "test.dummy"
