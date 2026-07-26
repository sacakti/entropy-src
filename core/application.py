"""
Application bootstrap.
"""

from pathlib import Path

from core.environment import Environment
from lib.output.output import OutputManager
from version import APP_NAME, VERSION
from lib.configuration.config_loader import config
from core.context import EntropyContext
from lib.workflow import Workflow
from lib.plugins.manager import PluginManager
from lib.executor import LinuxExecutor

class Application:

    def __init__(self):

        self.context = EntropyContext()

        self.context.plugin_manager = PluginManager(
            self.context
        )

        self.context.executor = LinuxExecutor()

    def initialize(self):

        Environment.prepare()

        output = OutputManager()
        
        output.initialize(Path("logs"))

        output.banner(APP_NAME, VERSION)
        
        output.system.info("Application started")

        output.system.success("Environment initialized")

        config.load()

        self.context.config = config

        workflow = Workflow(self.context)

        workflow.load("default")

        workflow.execute()
        