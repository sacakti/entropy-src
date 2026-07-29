"""
Application runtime context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.commands.manager import CommandManager
from lib.configuration.manager import ConfigurationManager
from lib.models.workflow import WorkflowDefinition
from lib.output.manager import OutputManager

if TYPE_CHECKING:
    from core.commands.manager import CommandManager
    from core.generators.manager import GeneratorManager
    from core.template.engine import TemplateEngine
    from lib.auth.manager import SessionManager
    from lib.configuration.manager import ConfigurationManager
    from lib.database.repositories.users import UserRepository
    from lib.output.manager import OutputManager
    from lib.plugins.manager import PluginManager
    from lib.users.manager import UserManager
    from lib.users.password import PasswordService


class EntropyContext:
    """
    Shared runtime context.

    This object is passed across the application instead of
    passing multiple objects individually.
    """

    def __init__(self):

        #
        # Application configuration
        #
        self.config = None

        #
        # Output manager
        #
        self.output = OutputManager()

        #
        # Current workflow
        #
        # self.workflow: Optional[dict] = None
        self.workflow: Optional[WorkflowDefinition] = None

        #
        # Current release
        #
        self.release = None

        #
        # Plugin manager
        #
        self.plugin_manager: PluginManager | None = None

        #
        # Linux Executor
        #
        self.executor = None

        #
        # Database manager
        #
        self.database_manager = None

        #
        # Application managers
        #
        self.command_manager: CommandManager | None = None
        self.configuration: ConfigurationManager | None = None
        self.user_manager: UserManager | None = None
        self.password_service: PasswordService | None = None
        self.user_repository: Optional[UserRepository] = None
        self.session_manager: Optional[SessionManager] = None
        self.generator_manager: Optional[GeneratorManager] = None
        self.template: Optional[TemplateEngine] = None
