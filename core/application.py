"""
Application bootstrap.
"""

from pathlib import Path

from core.environment import Environment
# from lib.console_bkp.console import console
# from lib.logger_bkp.logger import logger_manager
from lib.output.output import OutputManager
from version import APP_NAME, VERSION
from config.config_loader import config

class Application:

    def initialize(self):

        Environment.prepare()

        config.load()

        # logger_manager.initialize(Path("logs"))

        # logger = logger_manager.get_logger("entropy")

        # console.banner(APP_NAME, VERSION)

        # logger.info("Application started")

        # console.success("Environment initialized")
        output = OutputManager()

        output.initialize(Path("logs"))

        output.banner(APP_NAME, VERSION)

        output.system.info("Application started")

        output.system.success("Environment initialized")