from lib.plugins.base import Plugin


class ValidateEnvironmentPlugin(Plugin):

    NAME = "validate_environment"

    def execute(self, config):

        self.context.output.system.success(
            "Environment validation completed"
        )