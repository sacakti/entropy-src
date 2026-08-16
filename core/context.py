"""
Application runtime context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lib.normalizer.manager import NormalizerManager

if TYPE_CHECKING:
    from core.commands.manager import CommandManager
    from core.configuration.manager import ConfigurationManager
    from core.generators.manager import GeneratorManager
    from core.observability import ObservabilityManager
    from core.observability.console import LogConsoleSink
    from core.observability.logging import LoggingManager
    from core.paths.bootstrap import BootstrapPathManager
    from core.paths.manager import RuntimePathManager
    from core.runtime.manager import ExecutionManager
    from core.template.engine import TemplateEngine
    from core.ui import UIManager
    from lib.auth.manager import SessionManager
    from lib.auth.service import AuthenticationService
    from lib.database.manager import DatabaseManager
    from lib.database.repositories.users import UserRepository
    from lib.executor import LinuxExecutor
    from lib.extensions.manager import ExtensionManager
    from lib.migrations.manager import MigrationManager
    from lib.plugins.manager import PluginManager
    from lib.users.manager import UserManager
    from lib.users.password import PasswordService
    from lib.vault.manager import VaultManager
    from lib.workflow.jobs.manager import WorkflowJobManager
    from lib.workflow.manager import WorkflowManager
    from lib.workflow.runner import WorkflowRunner
    from lib.formatter import FormatterManager

class EntropyContext:
    """
    Shared application context.

    Acts as the application's dependency container.

    This object intentionally stores only shared services and
    infrastructure components. Runtime execution state belongs to
    Runtime/Execution, not the application context.
    """

    def __init__(self) -> None:

        # ---------------------------------------------------------
        # Bootstrap
        # ---------------------------------------------------------

        self.ui: UIManager | None = None

        self.bootstrap: BootstrapPathManager | None = None

        self.paths: RuntimePathManager | None = None

        # ---------------------------------------------------------
        # Infrastructure
        # ---------------------------------------------------------

        self.executor: LinuxExecutor | None = None

        self.observability: ObservabilityManager | None = None

        self.logging: LoggingManager | None = None

        self.console_log_sink: LogConsoleSink | None = None

        self.workflow_runner: WorkflowRunner | None = None

        # ---------------------------------------------------------
        # Core Managers
        # ---------------------------------------------------------

        self.configuration: ConfigurationManager | None = None

        self.database_manager: DatabaseManager | None = None

        self.migration_manager: MigrationManager | None = None

        self.extension_manager: ExtensionManager | None = None

        self.plugin_manager: PluginManager | None = None

        self.execution_manager: ExecutionManager | None = None

        self.workflow_manager: WorkflowManager | None = None

        self.workflow_job_manager: WorkflowJobManager | None = None

        # ---------------------------------------------------------
        # Application Managers
        # ---------------------------------------------------------

        self.command_manager: CommandManager | None = None

        self.generator_manager: GeneratorManager | None = None

        self.template: TemplateEngine | None = None

        # ---------------------------------------------------------
        # Services
        # ---------------------------------------------------------

        self.authentication: AuthenticationService | None = None

        self.password_service: PasswordService | None = None

        self.user_repository: UserRepository | None = None

        self.user_manager: UserManager | None = None

        self.session_manager: SessionManager | None = None

        self.vault_manager: VaultManager | None = None

        self.formatter: FormatterManager | None = None

        self.normalizer: NormalizerManager | None = None
