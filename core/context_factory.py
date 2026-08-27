"""
Entropy context factory.

Responsible for constructing the application dependency graph.
"""

from __future__ import annotations

from pathlib import Path

from core.commands.manager import CommandManager
from core.configuration import ConfigurationManager
from core.context import EntropyContext
from core.environment import Environment
from core.generators.manager import GeneratorManager
from core.models.logger import LogLevel
from core.observability import ObservabilityManager
from core.observability.console import ConsoleSink as ObservabilityConsoleSink
from core.observability.console import LogConsoleSink
from core.observability.console.renderer import ConsoleRenderer
from core.observability.logging import LogFileSink, LoggingManager, LoggingSink
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
from lib.authorization.group_manager import GroupManager
from lib.authorization.user_role_manager import UserRoleManager
from lib.database.repositories.group_roles import GroupRoleRepository
from lib.database.repositories.groups import GroupRepository
from lib.database.repositories.permissions import PermissionRepository
from lib.database.repositories.role_permissions import RolePermissionRepository
from lib.database.repositories.roles import RoleRepository
from lib.authorization.role_manager import RoleManager
from lib.authorization.service import AuthorizationService
from lib.database.manager import DatabaseManager
from lib.database.repositories.user_groups import UserGroupRepository
from lib.database.repositories.user_roles import UserRoleRepository
from lib.database.repositories.users import UserRepository
from lib.database.repositories.vault_namespace_access import VaultNamespaceAccessRepository
from lib.database.repositories.vault_namespaces import VaultNamespaceRepository
from lib.executor import LinuxExecutor
from lib.extensions.manager import ExtensionManager
from lib.formatter.manager import FormatterManager
from lib.migrations.manager import MigrationManager
from lib.normalizer.manager import NormalizerManager
from lib.plugins.manager import PluginManager
from lib.users.manager import UserManager
from lib.users.password import PasswordService
from lib.vault import (
    VaultKeyProvider,
    VaultManager,
    VaultRepository,
    VaultSerializer,
)
from lib.vault.namespace_manager import VaultNamespaceManager
from lib.workflow.codec.json import JsonWorkflowCodec
from lib.workflow.codec.registry import WorkflowCodecRegistry
from lib.workflow.codec.yaml import YamlWorkflowCodec
from lib.workflow.jobs.manager import WorkflowJobManager
from lib.workflow.jobs.sink import WorkflowEventSink
from lib.workflow.manager import WorkflowManager
from lib.workflow.runner import WorkflowRunner

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
        interactive: bool = True,
    ) -> None:

        self._project_root = project_root
        self._entropy_home = entropy_home
        self._interactive = interactive

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

        self._context.formatter = FormatterManager(
            self._context.executor,
        )

        self._context.normalizer = NormalizerManager(
            self._context.executor,
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

        # console = ObservabilityConsoleSink(
        #     renderer,
        # )

        # observability.register(
        #     console,
        # )

        if self._interactive:

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
            level=self._context.configuration.get(
                "logging.level",
                "INFO",
            ),
        )

        self._context.logging = log_manager

        observability.register(
            LoggingSink(
                log_manager,
            ),
        )

        assert self._context.paths is not None

        observability.register(
            LogFileSink(
                manager=log_manager,
                log_file=self._context.paths.logs.entropy,
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

    def infrastructure(
        self,
    ) -> None:

        assert self._context.executor is not None

        #
        # Database
        #

        self._context.database_manager = DatabaseManager(
            self._context,
        )

        assert self._context.database_manager is not None

        self._context.database_manager.open()

        #
        # Extensions / migrations
        #

        self._context.extension_manager = ExtensionManager(
            self._context,
        )

        self._context.migration_manager = MigrationManager(
            self._context,
        )

        #
        # Plugins
        #

        self._context.plugin_manager = PluginManager(
            self._context,
        )

        #
        # Execution
        #

        self._context.execution_manager = ExecutionManager(
            self._context,
        )

        self._context.workflow_job_manager = WorkflowJobManager(
            self._context,
        )

        #
        # Workflow codecs
        #

        self._context.workflow_codecs = WorkflowCodecRegistry(
            [
                JsonWorkflowCodec(
                    self._context.executor,
                ),
                YamlWorkflowCodec(
                    self._context.executor,
                ),
            ],
        )

        #
        # Workflow runner
        #

        assert self._context.plugin_manager is not None

        self._context.workflow_runner = WorkflowRunner(
            context=self._context,
            plugin_runner=self._context.plugin_manager.runner,
        )

        #
        # Workflow manager
        #

        self._context.workflow_manager = WorkflowManager(
            self._context,
        )

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def services(self) -> None:

        assert self._context.database_manager is not None
        assert self._context.executor is not None
        assert self._context.paths is not None

        self._context.password_service = PasswordService()

        self._context.user_repository = UserRepository(
            self._context.database_manager.connection,
        )

        connection = self._context.database_manager.connection

        self._context.authorization = AuthorizationService(
            connection,
        )

        self._context.role_repository = RoleRepository(
            connection,
        )

        self._context.user_role_repository = UserRoleRepository(
            connection,
        )

        self._context.permission_repository = PermissionRepository(
            connection,
        )

        self._context.role_permission_repository = RolePermissionRepository(
            connection,
        )

        self._context.group_repository = GroupRepository(
            connection,
        )

        self._context.user_group_repository = UserGroupRepository(
            connection,
        )

        self._context.group_role_repository = GroupRoleRepository(
            connection,
        )

        self._context.vault_namespace_repository = VaultNamespaceRepository(
            connection,
        )

        self._context.vault_namespace_access_repository = VaultNamespaceAccessRepository(
            connection,
        )

        self._context.role_manager = RoleManager(
            roles=self._context.role_repository,
            permissions=self._context.permission_repository,
            role_permissions=self._context.role_permission_repository,
        )

        self._context.group_manager = GroupManager(
            groups=self._context.group_repository,
            users=self._context.user_repository,
            roles=self._context.role_repository,
            user_groups=self._context.user_group_repository,
            group_roles=self._context.group_role_repository,
        )

        self._context.vault_namespace_manager = VaultNamespaceManager(
            namespaces=self._context.vault_namespace_repository,
            access=self._context.vault_namespace_access_repository,
            users=self._context.user_repository,
        )

        self._context.user_manager = UserManager(
            self._context,
        )

        self._context.user_role_manager = UserRoleManager(
            roles=self._context.role_repository,
            user_roles=self._context.user_role_repository,
        )

        self._context.authentication = AuthenticationService(
            self._context,
        )

        self._context.session_manager = SessionManager(
            self._context,
        )

        #
        # Vault
        #

        vault_repository = VaultRepository(
            self._context.database_manager.connection,
        )

        vault_serializer = VaultSerializer()

        vault_key_provider = VaultKeyProvider(
            executor=self._context.executor,
            path=self._context.bootstrap.vault.key,
        )

        self._context.vault_manager = VaultManager(
            repository=vault_repository,
            serializer=vault_serializer,
            key_provider=vault_key_provider,
            namespace_manager=self._context.vault_namespace_manager,
        )

    # ------------------------------------------------------------------
    # Workflow Observability
    # ------------------------------------------------------------------

    def workflow_observability(self) -> None:
        """
        Connect workflow event persistence to observability.
        """

        assert self._context.observability is not None
        assert self._context.workflow_job_manager is not None

        self._context.observability.register(
            WorkflowEventSink(
                self._context.workflow_job_manager,
            )
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
        self.workflow_observability()
        self.services()
        self.application()

        return self._context
