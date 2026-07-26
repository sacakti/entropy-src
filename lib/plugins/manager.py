"""
Plugin manager.
"""

from __future__ import annotations

from lib.plugins.validate_environment import ValidateEnvironmentPlugin


class PluginManager:

    def __init__(self, context):

        self.context = context

        self._plugins = {}

        self.register(ValidateEnvironmentPlugin)

    def register(self, plugin):

        self._plugins[plugin.NAME] = plugin

    def execute(self, step):

        name = step["plugin"]

        plugin = self._plugins.get(name)

        if plugin is None:

            raise RuntimeError(
                f"Unknown plugin '{name}'"
            )

        instance = plugin(self.context)

        instance.execute(
            step.get("config", {})
        )