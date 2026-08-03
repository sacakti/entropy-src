from pathlib import Path
import shutil


class InstallerPathManager:

    def __init__(self) -> None:

        self.project_root = Path(__file__).resolve().parents[2]

        #
        # Application
        #

        self.application = self.project_root / "entropy.py"

        #
        # Entropy Home
        #

        self.home = Path.home() / ".entropy"
        self.staging = Path.home() / ".entropy.tmp"

        #
        # Runtime Directories
        #

        self.config = self.staging / "config"
        self.database = self.staging / "database"
        self.logs = self.staging / "logs"
        self.runtime = self.staging / "runtime"
        self.session = self.staging / "session"
        self.packages = self.staging / "site-packages"
        self.workflow = self.staging / "workflow"
        self.plugins = self.staging / "plugins"
        self.repository = self.staging / "repository"

        #
        # Installation Resources
        #

        self.vendor = self.project_root / "resources" / "wheels"

        self.requirements = self.vendor / "requirements.txt"

        self.default_config = (
            self.project_root
            / "lib"
            / "install"
            / "entropy.json.config"
        )

        self.default_workflow = (
            self.project_root
            / "lib"
            / "install"
            / "default.workflow.json.config"
        )

        #
        # Configuration
        #

        self.config_file = self.config / "entropy.json"
        self.workflow_file = self.workflow / "default.json"
        self.entropy_config = self.home / "config" / "entropy.json"

        #
        # Launcher
        #

        self.launcher_unix = Path.home() / ".local" / "bin" / "ent"

        self.launcher_windows = (
            Path.home()
            / "AppData"
            / "Local"
            / "Programs"
            / "Entropy"
            / "ent.cmd"
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

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    @property
    def directories(self) -> tuple[Path, ...]:
        """
        Runtime directories that must exist after installation.
        """

        return (
            self.staging,
            self.config,
            self.database,
            self.logs,
            self.runtime,
            self.session,
            self.packages,
            self.workflow,
            self.plugins,
            self.repository,
        )
