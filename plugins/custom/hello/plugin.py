from lib.plugins.base import BasePlugin


class HelloPlugin(BasePlugin):

    def execute(
        self,
        **kwargs,
    ) -> None:

        print("Hello Plugin 2")
