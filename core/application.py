"""
Application bootstrap.
"""

from pathlib import Path
import argparse

from core.constants import PLUGIN_DIR
from core.generators.manager import GeneratorManager
from version import APP_NAME, VERSION

from core.context import EntropyContext
from core.environment import Environment
from core.commands.manager import CommandManager

from lib.configuration.config_loader import config
from lib.executor import LinuxExecutor
from lib.output.output import OutputManager
from lib.plugins.manager import PluginManager
from core.template import PluginTemplates
from core.template import TemplateEngine

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

        self.context.generator_manager.discover()

    def run(self) -> None:

        self.context.command_manager.run()