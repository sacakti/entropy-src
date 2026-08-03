"""
Entropy context factory.

Responsible for constructing the application dependency graph.
"""

from __future__ import annotations

from pathlib import Path

from core.commands.manager import CommandManager
from core.configuration import ConfigurationManager
from core.context import EntropyContext
from core.diagnostics.manager import DiagnosticsManager
from core.environment import Environment
from core.generators.manager import GeneratorManager
from core.observability import ObservabilityManager
from core.diagnostics.console import ConsoleSink as DiagnosticsConsoleSink
from core.observability.console import ConsoleSink as ObservabilityConsoleSink, LogConsoleSink
from core.observability.console.renderer import ConsoleRenderer
from core.observability.logging import LoggingManager, LoggingSink, LogFileSink
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
from core.models.logger import LogLevel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTROPY_HOME = Path.home() / ".entropy"


class ContextFactory:
    """
    Builds an EntropyContext.
    """

    def __init__(
        self,
        *,
        project_root: Path = PROJECT_ROOT,
        entropy_home: Path = ENTROPY_HOME,
    ) -> None:

        self._project_root = project_root
        self._entropy_home = entropy_home

        self._context = EntropyContext()

    @property
    def context(self) -> EntropyContext:

        return self._context

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap(self) -> None:

        self._context.executor = LinuxExecutor()

        self._context.bootstrap = BootstrapPathManager(
            project_root=self._project_root,
            entropy_home=self._entropy_home,
        )

        self._context.configuration = ConfigurationManager(
            self._context,
        )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    def runtime(self) -> None:

        assert self._context.executor is not None
        assert self._context.bootstrap is not None
        assert self._context.configuration is not None

        #
        # Load application configuration.
        #
        self._context.configuration.load()

        #
        # Resolve runtime paths.
        #
        self._context.paths = RuntimePathManager(
            bootstrap=self._context.bootstrap,
            configuration=self._context.configuration.configuration,
        )

        #
        # Prepare runtime directories.
        #
        Environment(
            self._context.executor,
        ).prepare(
            self._context.paths,
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def observability(self) -> None:

        assert self._context.paths is not None
        assert self._context.configuration is not None

        # # ---- Start deprecation

        # diagnostics = DiagnosticsManager()

        # diagnostics.register(
        #     DiagnosticsConsoleSink(),
        # )

        # self._context.diagnostics = diagnostics

        # # ---- End deprecation

        observability = ObservabilityManager()

        renderer = ConsoleRenderer()

        console = ObservabilityConsoleSink(
            renderer,
        )

        observability.register(
            console,
        )

        console_log_sink = LogConsoleSink(
            renderer,
            level=LogLevel[
                self._context.configuration.get(
                    "console.level",
                    "INFO",
                ).upper()
            ],
        )

        observability.register(
            console_log_sink,
        )

        self._context.console_log_sink = console_log_sink

        log_manager = LoggingManager(
            directory=self._context.paths.logs.root,
            level=self._context.configuration.get(
                "logging.level",
                "INFO",
            ),
        )

        observability.register(
            LoggingSink(
                log_manager,
            ),
        )

        observability.register(
            LogFileSink(
                log_manager,
            ),
        )

        self._context.observability = observability

        if self._context.configuration.get(
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

    def infrastructure(self) -> None:

        self._context.database_manager = DatabaseManager(
            self._context,
        )

        assert self._context.database_manager is not None

        self._context.database_manager.open()

        self._context.execution_manager = ExecutionManager(
            self._context,
        )

        self._context.workflow_manager = WorkflowManager(
            self._context,
        )

        self._context.plugin_manager = PluginManager(
            self._context,
        )

        self._context.migration_manager = MigrationManager(
            self._context,
        )

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def services(self) -> None:

        assert self._context.database_manager is not None

        self._context.password_service = PasswordService()

        self._context.user_repository = UserRepository(
            self._context.database_manager.connection,
        )

        self._context.user_manager = UserManager(
            self._context,
        )

        self._context.authentication = AuthenticationService(
            self._context,
        )

        self._context.session_manager = SessionManager(
            self._context,
        )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    def application(self) -> None:

        self._context.command_manager = CommandManager(
            self._context,
        )

        self._context.generator_manager = GeneratorManager(
            self._context,
        )

        self._context.template = TemplateEngine(
            self._context,
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> None:

        assert self._context.plugin_manager is not None
        assert self._context.command_manager is not None
        assert self._context.generator_manager is not None

        self._context.plugin_manager.discover()

        self._context.command_manager.discover()

        self._context.generator_manager.discover()


    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def ui(self) -> None:
        """
        Initialize the user interface.
        """

        renderer = RichRenderer()

        prompt = PromptManager(
            renderer.console,
        )

        self._context.ui = UIManager(
            renderer=renderer,
            prompt=prompt,
        )

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> EntropyContext:
        """
        Build the complete application context.
        """

        self.bootstrap()
        self.runtime()
        self.observability()
        self.ui()
        self.infrastructure()
        self.services()
        self.application()

        return self._context
