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

        self.backup = Path.home() / ".entropy.backup"

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
        """
        Promote the staged Entropy home to the active home directory.

        The existing installation is preserved until the staged installation
        has been successfully promoted.
        """

        if not self.staging.exists():
            raise RuntimeError(
                f"Staging directory does not exist: {self.staging}",
            )

        if not self.staging.is_dir():
            raise RuntimeError(
                f"Staging path is not a directory: {self.staging}",
            )

        backup_created = False

        try:
            if self.backup.exists():
                shutil.rmtree(self.backup)

            if self.home.exists():
                self.home.rename(self.backup)
                backup_created = True

            try:
                self.staging.rename(self.home)
            except Exception:
                if backup_created and not self.home.exists():
                    self.backup.rename(self.home)

                raise

            if self.backup.exists():
                shutil.rmtree(self.backup)

        except Exception as exc:
            raise RuntimeError(
                f"Failed to commit Entropy installation: {exc}",
            ) from exc

    def rollback(self) -> None:
        """
        Remove staging data and restore the previous Entropy installation
        when a backup exists.
        """

        if self.staging.exists():
            shutil.rmtree(self.staging)

        if self.backup.exists() and not self.home.exists():
            self.backup.rename(self.home)

    def commit_application(self) -> None:
        """
        Promote the staged application to the active application root.

        The existing application is preserved until the staged application
        has been successfully promoted.
        """

        if not self.application_staging.exists():
            raise RuntimeError(
                "Application staging directory does not exist: "
                f"{self.application_staging}",
            )

        if not self.application_staging.is_dir():
            raise RuntimeError(
                "Application staging path is not a directory: "
                f"{self.application_staging}",
            )

        self.application_directory.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        backup_path = self.application_root / "application.backup"

        backup_created = False

        try:
            if backup_path.exists():
                shutil.rmtree(backup_path)

            if self.application_directory.exists():
                self.application_directory.rename(backup_path)
                backup_created = True

            try:
                self.application_staging.rename(
                    self.application_directory,
                )
            except Exception:
                if (
                    backup_created
                    and not self.application_directory.exists()
                ):
                    backup_path.rename(
                        self.application_directory,
                    )

                raise

            if backup_path.exists():
                shutil.rmtree(backup_path)

        except Exception as exc:
            raise RuntimeError(
                "Failed to commit application installation: "
                f"{exc}",
            ) from exc

    def rollback_application(self) -> None:
        """
        Remove application staging data and restore the previous application
        when a backup exists.
        """

        if self.application_staging.exists():
            shutil.rmtree(self.application_staging)

        backup_path = self.application_root / "application.backup"

        if backup_path.exists() and not self.application_directory.exists():
            backup_path.rename(self.application_directory)

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
