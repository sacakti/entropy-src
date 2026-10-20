"""
Entropy installer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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


@dataclass
class InstallOptions:
    """
    Choices for one installation. Anything left as None is asked for
    interactively (or fails when `interactive` is False).
    """

    workspace: Optional[Path] = None
    admin_username: Optional[str] = None
    admin_full_name: str = "Administrator"
    admin_password: Optional[str] = field(default=None, repr=False)
    # bundled: offline from the package's wheels; index: from a package
    # index; manual: already installed into the runtime Python.
    deps: str = "bundled"
    index_url: Optional[str] = None
    # A self-contained Python shipped in the package, copied next to the
    # application and used as the runtime.
    bundled_python: Optional[Path] = None
    platform: Optional[str] = None
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    # auto: systemd user service when available, else a background process.
    service: str = "auto"
    start_web: bool = True
    interactive: bool = True


class Installer:

    def __init__(self, options: InstallOptions | None = None) -> None:

        self._paths: InstallerPathManager | None = None
        self._options = options or InstallOptions()
        self._runtime_python = Path(sys.executable)

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

            console.step(self._deps_step())

            WheelInstaller(
                platform,
                paths,
                mode=self._options.deps,
                index_url=self._options.index_url,
            ).install()

            console.success("Python packages ready.")

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
                username=self._options.admin_username,
                password=self._options.admin_password,
                full_name=self._options.admin_full_name,
                interactive=self._options.interactive,
            ).install()
            # The password is not needed past this point.
            self._options.admin_password = None

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

            self._install_runtime_python(paths)
            self._write_record(paths)

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

            web_message = self._start_web()

            console.success("Installation completed.")

            return InstallerResult(
                success=True,
                message=(
                    "Entropy installed successfully.\n\n"
                    f"Installation Directory\n{paths.home}\n\n"
                    f"Application\n{paths.application_directory}\n\n"
                    f"Workspace\n{paths.workspace}\n\n"
                    f"Configuration\n"
                    f"{paths.home / 'config' / 'entropy.json'}\n\n"
                    f"Launcher\n{launcher}\n\n"
                    f"{web_message}\n\n"
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

        if paths.application_directory.exists():

            raise RuntimeError(
                "Entropy application is already installed at "
                f"'{paths.application_directory}'. Use 'ent upgrade --source <package>' "
                "to upgrade it.",
            )

        # Never replace an existing Entropy home (users, Vault, history).
        if (paths.home / "database").exists():

            raise RuntimeError(
                f"An Entropy home with data already exists at '{paths.home}'. "
                "Move it away first, or upgrade the existing installation.",
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

        if self._options.workspace is not None:

            return self._validate_workspace(
                self._options.workspace,
            ).resolve()

        if not self._options.interactive:

            raise RuntimeError("--workspace is required for a non-interactive installation.")

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
    # Runtime Python, record and web server
    # ------------------------------------------------------------------

    def _deps_step(self) -> str:

        return {
            "bundled": "Installing Python packages from the bundled wheels...",
            "index": "Installing Python packages from the package index...",
            "manual": "Checking manually installed Python packages...",
        }.get(self._options.deps, "Installing Python packages...")

    def _install_runtime_python(self, paths: InstallerPathManager) -> None:
        """Copy the package's self-contained Python next to the application."""

        source = self._options.bundled_python

        if source is None or not source.is_dir():

            console.success(f"Using Python {sys.version.split()[0]} at {sys.executable}.")
            return

        console.step("Installing the bundled Python runtime...")

        destination = paths.application_root / "python"

        if destination.exists():
            shutil.rmtree(destination)

        shutil.copytree(source, destination, symlinks=True)

        relative = Path(sys.executable).resolve().relative_to(source.resolve())
        self._runtime_python = destination / relative

        console.success(f"Python runtime installed at {destination}.")

    def _write_record(self, paths: InstallerPathManager) -> None:

        from core.version import VERSION

        record = {
            "version": VERSION,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "python": str(self._runtime_python),
            "deps": self._options.deps,
            "index_url": self._options.index_url,
            "platform": self._options.platform,
            "application": str(paths.application_directory),
            "web": {
                "host": self._options.web_host,
                "port": int(self._options.web_port),
                "service": "process",
            },
            "upgrades": [],
        }

        (paths.config / "install.json").write_text(
            json.dumps(record, indent=2) + "\n",
            encoding="utf-8",
        )

    def _start_web(self) -> str:
        """Register the web server as a service when possible, then start it."""

        from lib.system import install, web

        record = install.load()
        service = self._options.service

        if service in ("auto", "systemd") and os.name != "nt":

            available = (
                shutil.which("systemctl") is not None
                and subprocess.run(
                    ["systemctl", "--user", "show-environment"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode
                == 0
            )

            if available:

                console.step("Registering the web server as a systemd user service...")
                unit = web.service_file()
                unit.parent.mkdir(parents=True, exist_ok=True)
                unit.write_text(web.unit(record), encoding="utf-8")
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
                subprocess.run(
                    ["systemctl", "--user", "enable", web.SERVICE_NAME],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                # Keep it running after logout when the system allows it.
                subprocess.run(
                    ["loginctl", "enable-linger", os.environ.get("USER", "")],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                record["web"]["service"] = "systemd"
                install.save(record)
                console.success(f"Service {web.SERVICE_NAME} registered.")

            elif service == "systemd":

                console.error(
                    "systemd user services are not available; using a background process."
                )

        if not self._options.start_web:

            return (
                "Web Server\n" f"Start it with 'ent web start'; it will listen on {web.url(record)}"
            )

        console.step("Starting the web server...")
        state = web.start()

        if state["healthy"]:

            console.success(f"Web server running at {state['url']}.")
            return f"Web Server\n{state['url']} (manage with 'ent web start|stop|status')"

        console.error(f"The web server did not answer yet; see {state['log']}.")
        return f"Web Server\nNot answering yet; check {state['log']} and run 'ent web status'."

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
            python=self._runtime_python,
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
