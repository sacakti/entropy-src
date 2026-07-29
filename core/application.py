"""
Application bootstrap.
"""

from __future__ import annotations

from pathlib import Path

from core.commands.manager import CommandManager
from core.context import EntropyContext
from core.environment import Environment
from core.generators.manager import GeneratorManager
from core.template import TemplateEngine
from core.version import APP_NAME, VERSION
from lib.auth.manager import SessionManager
from lib.configuration import ConfigurationManager
from lib.database.manager import DatabaseManager
from lib.database.repositories.users import UserRepository
from lib.executor import LinuxExecutor
from lib.output.manager import OutputManager
from lib.plugins.manager import PluginManager
from lib.users.manager import UserManager
from lib.users.password import PasswordService


class Application:

    def __init__(self):

        self.context = EntropyContext()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap(self) -> None:

        self._bootstrap_core()

        self._bootstrap_managers()

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    def initialize(self) -> None:

        self._initialize_environment()

        self._initialize_output()

        self._initialize_database()

        self._initialize_services()

        self._discover()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:

        self.context.command_manager.run()

    # ------------------------------------------------------------------
    # Bootstrap Core
    # ------------------------------------------------------------------

    def _bootstrap_core(self) -> None:

        self.context.configuration = ConfigurationManager()

        self.context.executor = LinuxExecutor()

        self.context.output = OutputManager()

        self.context.password_service = PasswordService()

    # ------------------------------------------------------------------
    # Bootstrap Managers
    # ------------------------------------------------------------------

    def _bootstrap_managers(self) -> None:

        self.context.database_manager = DatabaseManager(
            self.context,
        )

        self.context.plugin_manager = PluginManager(
            self.context,
        )

        self.context.command_manager = CommandManager(
            self.context,
        )

        self.context.generator_manager = GeneratorManager(
            self.context,
        )

        self.context.template = TemplateEngine(
            self.context,
        )

    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------

    def _initialize_environment(self) -> None:

        Environment.prepare()

        self.context.configuration.load()

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _initialize_output(self) -> None:

        self.context.output.initialize(
            log_directory=Path(
                self.context.configuration.get(
                    "logging.directory"
                )
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

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _initialize_database(self) -> None:

        self.context.database_manager.initialize()

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def _initialize_services(self) -> None:

        #
        # Repositories
        #

        self.context.user_repository = UserRepository(
            self.context.database_manager.connection,
        )

        #
        # Managers
        #

        self.context.user_manager = UserManager(
            self.context,
        )

        self.context.session_manager = SessionManager(
            self.context,
        )

        #
        # Initialize managers
        #

        self.context.user_manager.initialize()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover(self) -> None:

        self.context.command_manager.discover()

        self.context.generator_manager.discover()

        self.context.plugin_manager.discover()
