"""
Runtime path manager.

Provides all runtime filesystem paths after the application
configuration has been loaded.
"""

from pathlib import Path
from typing import Union

from core.models.paths import (
    DatabasePaths,
    ExtensionPaths,
    GitPaths,
    LogPaths,
    PluginPaths,
    PythonPaths,
    SessionPaths,
    WorkflowPaths,
    WorkspacePaths,
)
from lib.models.configuration import ConfigurationModel

from .bootstrap import BootstrapPathManager


class RuntimePathManager:
    """
    Runtime path manager.

    Responsible for all configuration-driven runtime paths.
    """

    def __init__(
        self,
        configuration: ConfigurationModel,
        bootstrap: BootstrapPathManager,
    ) -> None:

        self._configuration = configuration
        self._bootstrap = bootstrap

        self._database = self._build_database_paths()
        self._extensions = self._build_extension_paths()
        self._session = self._build_session_paths()
        self._python = self._build_python_paths()
        self._logs = self._build_log_paths()
        self._workflow = self._build_workflow_paths()
        self._git = self._build_git_paths()
        self._plugins = self._build_plugin_paths()
        self._workspace = self._build_workspace_paths()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def database(self) -> DatabasePaths:
        return self._database

    @property
    def extensions(self) -> ExtensionPaths:
        return self._extensions

    # @property
    # def runtime(self) -> RuntimePaths:
    #     return self._runtime

    @property
    def session(self) -> SessionPaths:
        return self._session

    @property
    def python(self) -> PythonPaths:
        return self._python

    @property
    def logs(self) -> LogPaths:
        return self._logs

    @property
    def workflow(self) -> WorkflowPaths:
        return self._workflow

    @property
    def git(self) -> GitPaths:
        return self._git

    @property
    def plugins(self) -> PluginPaths:
        return self._plugins

    @property
    def workspace(self) -> WorkspacePaths:
        return self._workspace

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    def _build_database_paths(
        self,
    ) -> DatabasePaths:

        database = self._resolve(
            self._configuration.get(
                "database.path",
            )
        )

        return DatabasePaths(
            directory=database.parent,
            file=database,
        )

    def _build_extension_paths(
        self,
    ) -> ExtensionPaths:

        root = self._bootstrap.home / "extensions"

        return ExtensionPaths(
            root=root,
            wheels=root / "wheels",
            site_packages=root / "site-packages",
            cache=root / "cache",
            downloads=root / "downloads",
        )

    def _build_session_paths(
        self,
    ) -> SessionPaths:

        directory = self._resolve(
            self._configuration.get(
                "session.directory",
            )
        )

        return SessionPaths(
            directory=directory,
            current=directory / "current.json",
        )

    def _build_python_paths(
        self,
    ) -> PythonPaths:

        packages = self._resolve(
            self._configuration.get(
                "python.packages",
            )
        )

        return PythonPaths(
            packages=packages,
        )

    def _build_log_paths(
        self,
    ) -> LogPaths:

        root = self._resolve(
            self._configuration.get(
                "logging.directory",
            )
        )

        return LogPaths(
            root=root,
            entropy=root / "entropy.log",
            plugins=root / "plugins.log",
            integrations=root / "integrations.log",
            workflows=root / "workflows.log",
        )

    def _build_workflow_paths(
        self,
    ) -> WorkflowPaths:

        return WorkflowPaths(
            default=self._configuration.get(
                "workflow.default",
            ),
        )

    def _build_git_paths(
        self,
    ) -> GitPaths:

        repository = self._resolve(
            self._configuration.get(
                "git.repository",
            )
        )

        return GitPaths(
            repository=repository,
        )

    def _build_plugin_paths(
        self,
    ) -> PluginPaths:

        directory = self._resolve(
            self._configuration.get(
                "plugins.directory",
            )
        )

        return PluginPaths(
            directory=directory,
        )

    def _build_workspace_paths(
        self,
    ) -> WorkspacePaths:

        root = self._resolve_workspace(
            self._configuration.get(
                "workspace.root",
            )
        )

        return WorkspacePaths(
            root=root,
            workflows=root / "workflows",
            executions=root / "executions",
            generated=root / "generated",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve(
        self,
        path: Union[str, Path],
    ) -> Path:
        """
        Resolve a configured path.
        """

        if path is None:

            raise ValueError(
                "Configuration path is missing.",
            )

        path = Path(path)

        if path.is_absolute():

            return path

        return self._bootstrap.home / path

    def _resolve_workspace(
        self,
        path: Union[str, Path],
    ) -> Path:

        if path is None:
            raise ValueError(
                "Workspace root is missing.",
            )

        path = Path(path).expanduser()

        if not path.is_absolute():
            raise ValueError(
                "Workspace root must be an absolute path.",
            )

        return path
