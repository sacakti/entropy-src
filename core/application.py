"""
Application bootstrap.
"""

from pathlib import Path

from core.environment import Environment
from lib.console.console import console
from lib.logger.logger import logger_manager
from version import APP_NAME, VERSION


class Application:

    def initialize(self):

        Environment.prepare()

        logger_manager.initialize(Path("logs"))

        logger = logger_manager.get_logger("entropy")

        console.banner(APP_NAME, VERSION)

        logger.info("Application started")

        console.success("Environment initialized")