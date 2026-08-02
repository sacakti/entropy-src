from unittest.mock import Mock

from lib.plugins.plugin import Plugin


class LifecyclePlugin(Plugin):

    def __init__(self):

        self.calls = []

    @property
    def metadata(self):

        from lib.plugins.metadata import PluginMetadata

        return PluginMetadata(
            name="lifecycle",
            namespace="test",
            version="1.0",
            package="pkg",
            module="pkg.plugin",
        )

    def initialize(
        self,
        context,
    ):

        self.calls.append("initialize")

    def validate(
        self,
        step,
    ):

        self.calls.append("validate")

    def execute(
        self,
        context,
        step,
    ):

        self.calls.append("execute")

    def dispose(self):

        self.calls.append("dispose")


def test_plugin_lifecycle():

    plugin = LifecyclePlugin()

    plugin.run(
        Mock(),
        Mock(),
    )

    assert plugin.calls == [
        "initialize",
        "validate",
        "execute",
        "dispose",
    ]


def test_dispose_always_called():

    class BrokenPlugin(LifecyclePlugin):

        def execute(
            self,
            context,
            step,
        ):

            self.calls.append("execute")

            raise RuntimeError()

    plugin = BrokenPlugin()

    try:

        plugin.run(
            Mock(),
            Mock(),
        )

    except RuntimeError:

        pass

    assert plugin.calls == [
        "initialize",
        "validate",
        "execute",
        "dispose",
    ]
