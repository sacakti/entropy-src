"""
Entropy application.
"""

from __future__ import annotations

from pathlib import Path

from core.commands.manager import CommandManager
from core.configuration import ConfigurationManager
from core.context import EntropyContext
from core.diagnostics.console import ConsoleSink as DiagnosticsConsoleSink
from core.diagnostics.manager import DiagnosticsManager
from core.environment import Environment
from core.generators.manager import GeneratorManager
from core.observability import ObservabilityManager
from core.observability.console import ConsoleSink as ObservabilityConsoleSink
from core.observability.console.renderer import ConsoleRenderer
from core.observability.logging import LoggingManager, LoggingSink
from core.paths.bootstrap import BootstrapPathManager
from core.paths.manager import RuntimePathManager
from core.runtime.manager import ExecutionManager
from core.template import TemplateEngine
from core.ui import UIManager
from core.ui.prompt import PromptManager
from core.ui.rich_renderer import RichRenderer
from core.version import APP_NAME, VERSION
from lib.auth.manager import SessionManager
from lib.auth.service import AuthenticationService
from lib.database.manager import DatabaseManager
from lib.database.repositories.users import UserRepository
from lib.executor import LinuxExecutor
from lib.migrations.manager import MigrationManager
from lib.plugins.manager import PluginManager
from lib.users.manager import UserManager
from lib.users.password import PasswordService
from lib.workflow.manager import WorkflowManager

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTROPY_HOME = Path.home() / ".entropy"


class Application:
    """
    Entropy application.

    Responsible only for composing and initializing the application's
    infrastructure.
    """

    def __init__(self) -> None:

        self.context = EntropyContext()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def bootstrap(self) -> None:

        self._bootstrap()

    def initialize(self) -> None:

        self._initialize_runtime()

        self._initialize_observability()

        self._initialize_ui()

        self._initialize_infrastructure()

        self._initialize_services()

        self._initialize_application()

        self._discover()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _initialize_ui(self) -> None:
        """
        Initialize the user interface.
        """

        renderer = RichRenderer()

        prompt = PromptManager(
            renderer.console,
        )

        self.context.ui = UIManager(
            renderer=renderer,
            prompt=prompt,
        )

    def run(self) -> None:

        assert self.context.command_manager is not None

        self.context.command_manager.run()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _bootstrap(self) -> None:

        self.context.executor = LinuxExecutor()

        self.context.bootstrap = BootstrapPathManager(
            project_root=PROJECT_ROOT,
            entropy_home=ENTROPY_HOME,
        )

        self.context.configuration = ConfigurationManager(
            self.context,
        )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    def _initialize_runtime(self) -> None:

        assert self.context.executor is not None
        assert self.context.bootstrap is not None
        assert self.context.configuration is not None

        #
        # Load application configuration.
        #
        self.context.configuration.load()

        #
        # Resolve runtime paths.
        #
        self.context.paths = RuntimePathManager(
            bootstrap=self.context.bootstrap,
            configuration=self.context.configuration.configuration,
        )

        #
        # Prepare runtime directories.
        #
        Environment(
            self.context.executor,
        ).prepare(
            self.context.paths,
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def _initialize_observability(self) -> None:

        assert self.context.paths is not None
        assert self.context.configuration is not None

        diagnostics = DiagnosticsManager()

        diagnostics.register(
            DiagnosticsConsoleSink(),
        )

        # diagnostics.register(
        #     FileSink(
        #         self.context.paths.logs.system,
        #     )
        # )

        self.context.diagnostics = diagnostics

        observability = ObservabilityManager()

        renderer = ConsoleRenderer()

        console = ObservabilityConsoleSink(
            renderer,
        )

        observability.register(
            console,
        )

        log_manager = LoggingManager(
            directory=self.context.paths.logs.root,
            level=self.context.configuration.get(
                "logging.level",
                "INFO",
            ),
        )

        observability.register(
            LoggingSink(
                log_manager,
            ),
        )

        self.context.observability = observability

        if self.context.configuration.get(
            "console.banner",
            False,
        ):

            console.banner(
                APP_NAME,
                VERSION,
            )

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    def _initialize_infrastructure(self) -> None:

        self.context.database_manager = DatabaseManager(
            self.context,
        )

        assert self.context.database_manager is not None

        self.context.database_manager.initialize()

        self.context.execution_manager = ExecutionManager(
            self.context,
        )

        self.context.workflow_manager = WorkflowManager(
            self.context,
        )

        self.context.plugin_manager = PluginManager(
            self.context,
        )

        self.context.migration_manager = MigrationManager(
            self.context,
        )

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def _initialize_services(self) -> None:

        assert self.context.database_manager is not None

        self.context.password_service = PasswordService()

        self.context.user_repository = UserRepository(
            self.context.database_manager.connection,
        )

        self.context.user_manager = UserManager(
            self.context,
        )

        self.context.authentication = AuthenticationService(
            self.context,
        )

        self.context.session_manager = SessionManager(
            self.context,
        )

        self.context.user_manager.initialize()

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    def _initialize_application(self) -> None:

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
    # Discovery
    # ------------------------------------------------------------------

    def _discover(self) -> None:

        assert self.context.plugin_manager is not None
        assert self.context.command_manager is not None
        assert self.context.generator_manager is not None

        self.context.plugin_manager.discover()

        self.context.command_manager.discover()

        self.context.generator_manager.discover()
