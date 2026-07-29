from .executor import PluginExecutor
from .loader import PluginLoader
from .registry import PluginRegistry


class PluginManager:

    def __init__(self, context):

        self._registry = PluginRegistry(context)

        self._loader = PluginLoader(
            context,
            self._registry,
        )

        self._executor = PluginExecutor(
            context,
            self._loader,
        )

    def discover(self):

        self._registry.discover()

    def register(self, plugin):

        self._registry.register(plugin)

    def get(self, name):

        return self._registry.get(name)

    def list(self):

        return self._registry.list()

    def load(self, name):

        return self._loader.load(name)

    def execute(
        self,
        name,
        config,
    ):

        return self._executor.execute(
            name,
            config,
        )
