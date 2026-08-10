from __future__ import annotations

import shutil
from pathlib import Path


class InstallerPathManager:

    def __init__(
        self,
        workspace: Path | None = None,
    ) -> None:

        self.project_root = (
            Path(
                __file__,
            )
            .resolve()
            .parents[2]
        )

        self.workspace = workspace.expanduser().resolve() if workspace is not None else None

        #
        # Application
        #

        self.application = self.project_root / "entropy.py"

        self.application_root = Path.home() / ".local" / "share" / "entropy"

        self.application_directory = self.application_root / "application"

        self.application_staging = self.application_root / "staging"

        self.application_backup = self.application_root / "backups"

        self.installed_application = self.application_directory / "entropy.py"

        #
        # Entropy Home
        #

        self.home = Path.home() / ".entropy"

        self.staging = Path.home() / ".entropy.tmp"

        #
        # Persistent Entropy directories
        #

        self.config = self.staging / "config"

        self.database = self.staging / "database"

        self.logs = self.staging / "logs"

        self.session = self.staging / "session"

        self.packages = self.staging / "site-packages"

        self.plugins = self.staging / "plugins"

        self.repository = self.staging / "repository"

        #
        # Installation resources
        #

        self.vendor = self.project_root / "resources" / "wheels"

        self.requirements = self.vendor / "requirements.txt"

        self.default_config = self.project_root / "lib" / "install" / "entropy.json.config"

        self.default_workflow = (
            self.project_root / "lib" / "install" / "default.workflow.json.config"
        )

        #
        # Configuration
        #

        self.config_file = self.config / "entropy.json"

        #
        # Launcher
        #

        self.launcher_unix = Path.home() / ".local" / "bin" / "ent"

        self.launcher_windows = (
            Path.home() / "AppData" / "Local" / "Programs" / "Entropy" / "ent.cmd"
        )

    # ------------------------------------------------------------------
    # Transaction
    # ------------------------------------------------------------------

    def commit(self) -> None:

        if self.home.exists():
            shutil.rmtree(self.home)

        self.staging.rename(
            self.home,
        )

    def rollback(self) -> None:

        if self.staging.exists():

            shutil.rmtree(
                self.staging,
            )

    def commit_application(self) -> None:
        """
        Promote the staged application to the active application root.
        """

        if not self.application_staging.exists():

            raise RuntimeError(
                "Application staging directory does not exist: " f"{self.application_staging}",
            )

        if not self.application_staging.is_dir():

            raise RuntimeError(
                "Application staging path is not a directory: " f"{self.application_staging}",
            )

        if self.application_directory.exists():

            raise RuntimeError(
                "Application directory already exists: " f"{self.application_directory}",
            )

        self.application_directory.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.application_staging.rename(
            self.application_directory,
        )

    def rollback_application(self) -> None:

        if self.application_staging.exists():

            shutil.rmtree(
                self.application_staging,
            )

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    @property
    def directories(
        self,
    ) -> tuple[Path, ...]:
        """
        Persistent directories created during initial installation.
        """

        return (
            self.staging,
            self.config,
            self.database,
            self.logs,
            self.session,
            self.packages,
            self.plugins,
            self.repository,
        )
