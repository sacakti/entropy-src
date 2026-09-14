"""
Entropy installer.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from lib.authorization import AuthorizationInitializer
from lib.install.application import ApplicationInstaller
from lib.install.console import InstallerConsole
from lib.install.directory import DirectoryInstaller
from lib.install.paths import InstallerPathManager
from lib.install.plugins import DefaultPluginInstaller
from lib.install.workflow import DefaultWorkflowInstaller

from .launcher import Launcher
from .platform import PlatformDetector
from .wheels import WheelInstaller

console = InstallerConsole()


@dataclass
class InstallerResult:

    success: bool

    message: str


class Installer:

    def __init__(self) -> None:

        self._paths: InstallerPathManager | None = None

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def install(self) -> InstallerResult:

        try:

            #
            # Select workspace before building installation paths.
            #

            workspace = self._prompt_workspace()

            self._paths = InstallerPathManager(
                workspace,
            )

            paths = self._paths

            #
            # Validate fresh installation.
            #

            self._validate_installation(
                paths,
            )

            platform = PlatformDetector.detect()

            #
            # Install Python dependencies.
            #

            console.step("Installing Python packages...")

            WheelInstaller(
                platform,
                paths,
            ).install()

            console.success("Python packages installed.")

            #
            # Create Entropy staging directories.
            #

            console.step("Creating directories...")

            DirectoryInstaller(
                paths,
            ).install()

            console.success("Directories created.")

            #
            # Create configuration.
            #

            console.step("Installing configuration...")

            self._create_config()

            console.success("Configuration installed.")

            #
            # Build installation context.
            #

            sys.path.insert(
                0,
                str(paths.packages),
            )

            from core.context_factory import ContextFactory
            from lib.install.bootstrap import BootstrapInstaller
            from lib.install.database import DatabaseInstaller

            factory = ContextFactory(
                project_root=paths.project_root,
                entropy_home=paths.staging,
            )

            factory.bootstrap()

            factory.runtime()

            factory.observability()

            factory.ui()

            factory.infrastructure()

            #
            # Database.
            #

            console.step("Installing database...")

            DatabaseInstaller(
                factory.context,
            ).install()

            console.success("Database installed.")

            #
            # Bootstrap administrator.
            #

            console.step("Creating bootstrap administrator...")

            factory.services()

            admin_user = BootstrapInstaller(
                factory.context,
            ).install()

            console.success("Bootstrap administrator created.")

            #
            # Initialize authorization.
            #

            if admin_user is not None:

                console.step("Initializing authorization...")

                assert factory.context.database_manager is not None

                AuthorizationInitializer(
                    factory.context.database_manager.connection,
                ).initialize(
                    admin_user,
                )

                console.success("Authorization initialized.")

            #
            # Default plugins.
            #

            console.step("Installing default plugins...")

            DefaultPluginInstaller(
                factory.context,
            ).install()

            console.success("Default plugins installed.")

            #
            # Default workflow.
            #

            console.step("Installing default workflow...")

            DefaultWorkflowInstaller(
                factory.context,
            ).install()

            console.success("Default workflow installed.")

            #
            # Prepare persisted installation paths.
            #

            console.step("Finalizing installation paths...")

            assert factory.context.plugin_manager is not None

            factory.context.plugin_manager.finalize_installation(
                paths.staging,
                paths.home,
            )

            console.success("Installation paths finalized.")

            console.step("Installing application...")

            ApplicationInstaller(
                source=paths.project_root,
                destination=paths.application_staging,
            ).install()

            console.success("Application installed.")

            #
            # Activate installation.
            #

            console.step("Activating installation...")

            paths.commit()

            paths.commit_application()

            console.success("Installation activated.")

            #
            # Launcher.
            #

            console.step("Installing launcher...")

            launcher = self._install_launcher(
                platform,
                paths,
            )

            if not launcher.exists():

                raise RuntimeError(
                    "Failed to create launcher.",
                )

            console.success("Launcher installed.")

            #
            # Verify PATH.
            #

            console.step("Verifying PATH...")

            path_response = self._verify_path(
                launcher,
            )

            console.success("Installation completed.")

            return InstallerResult(
                success=True,
                message=(
                    "Entropy installed successfully.\n\n"
                    f"Installation Directory\n{paths.home}\n\n"
                    f"Workspace\n{paths.workspace}\n\n"
                    f"Configuration\n"
                    f"{paths.home / 'config' / 'entropy.json'}\n\n"
                    f"Launcher\n{launcher}\n\n"
                    f"{path_response}"
                ),
            )

        except Exception:

            if self._paths is not None:

                self._paths.rollback()

                self._paths.rollback_application()

            traceback.print_exc()

            return InstallerResult(
                success=False,
                message="Installation failed.",
            )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_installation(
        self,
        paths: InstallerPathManager,
    ) -> None:

        if paths.application_root.exists():

            raise RuntimeError(
                "Entropy application is already installed at " f"'{paths.application_root}'.",
            )

        if paths.application_staging.exists():

            raise RuntimeError(
                "Application staging directory already exists: " f"'{paths.application_staging}'.",
            )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _create_config(self) -> None:

        assert self._paths.workspace is not None

        with self._paths.default_config.open(
            "r",
            encoding="utf-8",
        ) as file:

            configuration = json.load(
                file,
            )

        configuration["workspace"]["root"] = str(
            self._paths.workspace,
        )

        self._paths.config_file.write_text(
            json.dumps(
                configuration,
                indent=4,
            )
            + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def _prompt_workspace(self) -> Path:

        default = Path(
            "/srv/workspace",
        )

        while True:

            value = input(
                f"Workflow workspace [{default}]: ",
            ).strip()

            workspace = default if not value else Path(value).expanduser()

            try:

                return self._validate_workspace(
                    workspace,
                ).resolve()

            except ValueError as exc:

                console.error(
                    str(exc),
                )

    def _validate_workspace(
        self,
        workspace: Path,
    ) -> Path:

        workspace = workspace.expanduser()

        if not workspace.is_absolute():

            raise ValueError(
                "Workspace path must be absolute.",
            )

        if workspace.exists():

            if not workspace.is_dir():

                raise ValueError(
                    f"Workspace path is not a directory: " f"{workspace}",
                )

        else:

            try:

                workspace.mkdir(
                    parents=True,
                    exist_ok=True,
                )

            except OSError as exc:

                raise ValueError(
                    f"Unable to create workspace " f"'{workspace}': {exc}",
                ) from exc

        if not workspace.is_dir():

            raise ValueError(
                f"Workspace path is not a directory: " f"{workspace}",
            )

        probe = workspace / ".entropy-write-test"

        try:

            probe.touch(
                exist_ok=False,
            )

            probe.unlink()

        except OSError as exc:

            raise ValueError(
                f"Workspace is not writable: " f"{workspace}",
            ) from exc

        return workspace

    # ------------------------------------------------------------------
    # Launcher
    # ------------------------------------------------------------------

    def _install_launcher(
        self,
        platform,
        paths: InstallerPathManager,
    ):

        return Launcher(
            platform,
            paths,
        ).install()

    # ------------------------------------------------------------------
    # PATH
    # ------------------------------------------------------------------

    def _verify_path(
        self,
        launcher: Path,
    ) -> str:

        launcher_dir = str(
            launcher.parent,
        )

        environment_paths = os.environ.get(
            "PATH",
            "",
        ).split(os.pathsep)

        shell = os.environ.get(
            "SHELL",
            "",
        )

        reload_cmd = "Restart your shell"

        if shell.endswith("zsh"):

            reload_cmd = "source ~/.zshrc"

        elif shell.endswith("bash"):

            reload_cmd = "source ~/.bashrc"

        if launcher_dir in environment_paths:

            return "You can now start Entropy by running:\n\n" "    ent\n"

        return (
            "The launcher directory is not on your PATH.\n\n"
            "Add the following line to your shell profile:\n\n"
            '    export PATH="$HOME/.local/bin:$PATH"\n\n'
            f"Then reload your shell with:\n\n"
            f"    {reload_cmd}\n\n"
            "or open a new terminal.\n"
        )
