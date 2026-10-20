"""
Prepare the Entropy home in a container, then start the web server.

The image holds the application (read only); everything that changes —
configuration, the SQLite database, sessions, plugins, logs and the
workflow workspace — lives under ENTROPY_HOME and ENTROPY_WORKSPACE, both
on the persistent volume. Every start runs `init`, which is idempotent:

- first start: creates the directories, configuration and database, the
  bootstrap administrator (ENTROPY_ADMIN_PASSWORD or
  ENTROPY_ADMIN_PASSWORD_FILE), and the default plugins and workflow;
- later starts (including a new image): applies database migrations.

    python -m lib.install.container init     prepare the volume only
    python -m lib.install.container serve    prepare it, then run the web server
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

DIRECTORIES = ("config", "database", "logs", "session", "site-packages", "plugins", "repository")
MARKER = "config/.container-initialized"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _home() -> Path:
    home = os.environ.get("ENTROPY_HOME")
    if not home:
        raise SystemExit("ENTROPY_HOME must point at the Entropy home on the persistent volume.")
    return Path(home)


def _workspace(home: Path) -> Path:
    return Path(os.environ.get("ENTROPY_WORKSPACE") or home.parent / "workspace")


def _admin_password() -> Optional[str]:
    """From ENTROPY_ADMIN_PASSWORD_FILE (a mounted secret) or ENTROPY_ADMIN_PASSWORD."""

    path = os.environ.get("ENTROPY_ADMIN_PASSWORD_FILE")
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip() or None
    return os.environ.pop("ENTROPY_ADMIN_PASSWORD", None) or None


def _write_config(home: Path, workspace: Path) -> None:
    config_file = home / "config" / "entropy.json"
    if config_file.exists():
        return
    template = _project_root() / "lib" / "install" / "entropy.json.config"
    configuration = json.loads(template.read_text(encoding="utf-8"))
    configuration["workspace"]["root"] = str(workspace)
    config_file.write_text(json.dumps(configuration, indent=4) + "\n", encoding="utf-8")


def initialize() -> Path:
    """Create or upgrade the Entropy home on the volume. Idempotent."""

    home = _home()
    workspace = _workspace(home)
    for name in DIRECTORIES:
        (home / name).mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    _write_config(home, workspace)

    from core.context_factory import ContextFactory
    from lib.install.database import DatabaseInstaller

    database = home / "database" / "entropy.db"
    fresh = not database.exists()

    factory = ContextFactory(project_root=_project_root(), entropy_home=home, interactive=False)
    factory.bootstrap()
    factory.runtime()
    factory.observability()
    factory.ui()
    factory.infrastructure()

    if fresh:
        print(f"Creating the database at {database}.", flush=True)
        DatabaseInstaller(factory.context).install()
    else:
        factory.context.migration_manager.migrate()

    factory.services()
    context = factory.context
    assert context.user_manager is not None

    if not context.user_manager.any():
        from lib.authorization import AuthorizationInitializer
        from lib.install.bootstrap import BootstrapInstaller

        password = _admin_password()
        if not password:
            raise SystemExit(
                "First start: set ENTROPY_ADMIN_PASSWORD (or ENTROPY_ADMIN_PASSWORD_FILE) "
                "for the bootstrap administrator."
            )
        admin = BootstrapInstaller(
            context,
            username=os.environ.get("ENTROPY_ADMIN_USER") or "admin",
            password=password,
            full_name=os.environ.get("ENTROPY_ADMIN_NAME") or "Administrator",
            interactive=False,
        ).install()
        if admin is not None:
            assert context.database_manager is not None
            AuthorizationInitializer(context.database_manager.connection).initialize(admin)

    marker = home / MARKER
    if not marker.exists():
        from lib.install.plugins import DefaultPluginInstaller
        from lib.install.workflow import DefaultWorkflowInstaller

        print("Installing the default plugins and workflow.", flush=True)
        DefaultPluginInstaller(context).install()
        DefaultWorkflowInstaller(context).install()
        marker.write_text("1\n", encoding="utf-8")

    return home


def main(argv: Optional[list] = None) -> int:
    command = (argv if argv is not None else sys.argv[1:] or ["serve"])[0]
    if command not in ("init", "serve"):
        print(__doc__)
        return 2

    home = initialize()
    print(f"Entropy home ready at {home}.", flush=True)
    if command == "init":
        return 0

    os.environ.setdefault("ENTROPY_WEB_HOST", "0.0.0.0")
    os.execv(sys.executable, [sys.executable, "-m", "core.web"])
    return 0  # pragma: no cover - execv does not return


if __name__ == "__main__":
    sys.exit(main())
