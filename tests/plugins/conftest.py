from unittest.mock import Mock

import pytest
from lib.plugins.metadata import PluginMetadata
from lib.plugins.plugin import Plugin


class DummyPlugin(Plugin):

    @property
    def metadata(self) -> PluginMetadata:

        return PluginMetadata(
            name="dummy",
            namespace="test",
            version="1.0",
            package="plugins.test.dummy",
            module="plugins.test.dummy.plugin",
        )

    def execute(
        self,
        context,
        step,
    ) -> None:

        context.executed = True


@pytest.fixture
def entropy_context():

    return Mock()


@pytest.fixture
def metadata():

    return PluginMetadata(
        name="dummy",
        namespace="test",
        version="1.0",
        package="plugins.test.dummy",
        module="plugins.test.dummy.plugin",
    )


@pytest.fixture
def plugin():

    return DummyPlugin()
