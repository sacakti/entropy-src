"""
Application bootstrap.
"""

from pathlib import Path
import argparse

from version import APP_NAME, VERSION

from core.context import EntropyContext
from core.environment import Environment
from core.commands.manager import CommandManager

from lib.configuration.config_loader import config
from lib.executor import LinuxExecutor
from lib.output.output import OutputManager
from lib.plugins.manager import PluginManager


class Application:

    def __init__(self):

        self.context = EntropyContext()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap(self) -> None:

        self.context.executor = LinuxExecutor()

        self.context.output = OutputManager()

        self.context.plugin_manager = PluginManager(
            self.context
        )

        self.context.command_manager = CommandManager(
            self.context
        )

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    def initialize(self) -> None:

        Environment.prepare()

        self.context.output.initialize(
            Path("logs")
        )

        self.context.output.banner(
            APP_NAME,
            VERSION,
        )

        self.context.output.system.info(
            "Application started"
        )

        self.context.output.system.success(
            "Environment initialized"
        )

        config.load()

        self.context.config = config

        self.context.command_manager.discover()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    # def run(self) -> None:

    #     parser = argparse.ArgumentParser(
    #         prog="entropy",
    #         add_help=False,
    #     )

    #     subparsers = parser.add_subparsers(
    #         dest="command",
    #     )

    #     for command in self.context.command_manager.list():

    #         subparser = subparsers.add_parser(
    #             command.metadata.name,
    #             help=command.metadata.description,
    #         )

    #         command.configure(subparser)

    #     args = parser.parse_args()

    #     command_name = args.command or "help"

    #     command = self.context.command_manager.get(
    #         command_name
    #     )

    #     command.execute(args)

    def run(self) -> None:

        self.context.command_manager.run()