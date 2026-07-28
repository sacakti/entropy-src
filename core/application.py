"""
Application bootstrap.
"""

from pathlib import Path
# import argparse

# from core.constants import PLUGIN_DIR
from core.generators.manager import GeneratorManager
from lib.database.manager import DatabaseManager
from version import APP_NAME, VERSION

from core.context import EntropyContext
from core.environment import Environment
from core.commands.manager import CommandManager

# from lib.configuration.config_loader import config
from lib.configuration import ConfigurationManager
from lib.executor import LinuxExecutor
from lib.output.output import OutputManager
from lib.plugins.manager import PluginManager
# from core.template import PluginTemplates
from core.template import TemplateEngine

class Application:

    def __init__(self):

        self.context = EntropyContext()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap(self) -> None:

        self.context.configuration = ConfigurationManager()

        self.context.database_manager = DatabaseManager(
            self.context
        )

        self.context.executor = LinuxExecutor()

        self.context.output = OutputManager()

        self.context.plugin_manager = PluginManager(
            self.context
        )

        self.context.command_manager = CommandManager(
            self.context
        )

        self.context.generator_manager = GeneratorManager(
            self.context
        )

        self.context.template = TemplateEngine(
            self.context,
        )
        
    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    def initialize(self) -> None:

        Environment.prepare()

        self.context.configuration.load()

        # self.context.config = config

        self.context.output.initialize(
            log_directory=Path(
                self.context.configuration.get("logging.directory")
            ),
            level=self.context.configuration.get(
                "logging.level",
                "INFO",
            ),
            console_level=self.context.configuration.get(
                "console.level",
                "NORMAL",
            ),
        )

        if self.context.configuration.get(
            "console.banner",
            False,
        ):
            self.context.output.banner(
                APP_NAME,
                VERSION,
            )

        self.context.output.system.debug(
            "Application started"
        )

        self.context.output.system.debug(
            "Environment initialized"
        )

        self.context.command_manager.discover()

        self.context.generator_manager.discover()

        self.context.plugin_manager.discover()
        
    def run(self) -> None:

        self.context.command_manager.run()
