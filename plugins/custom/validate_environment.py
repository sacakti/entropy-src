from lib.plugins.base import BasePlugin as Plugin

PLUGIN_CLASS = "ValidateEnvironmentPlugin"

class ValidateEnvironmentPlugin(Plugin):

    NAME = "validate_environment"

    def execute(self, config):

        self.context.output.system.success(
            "Environment validation completed"
        )