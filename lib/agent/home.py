"""
The node agent's own Entropy home: configuration, directories and the
local job database its worker processes use.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DIRECTORIES = ("config", "database", "logs", "session", "site-packages", "plugins", "repository")


def entropy_home() -> Path:
    home = os.environ.get("ENTROPY_HOME")
    if not home:
        raise SystemExit("ENTROPY_HOME must point at the agent's Entropy home.")
    return Path(home)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def initialize(workspace: Path) -> Path:
    """Create (or upgrade) the agent's Entropy home. Idempotent."""

    home = entropy_home()
    for name in DIRECTORIES:
        (home / name).mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)

    config_file = home / "config" / "entropy.json"
    if not config_file.exists():
        template = project_root() / "lib" / "install" / "entropy.json.config"
        configuration = json.loads(template.read_text(encoding="utf-8"))
        configuration["workspace"]["root"] = str(workspace)
        configuration["console"]["banner"] = False
        config_file.write_text(json.dumps(configuration, indent=4) + "\n", encoding="utf-8")

    from core.context_factory import ContextFactory
    from lib.install.database import DatabaseInstaller

    database = home / "database" / "entropy.db"
    fresh = not database.exists()

    factory = ContextFactory(project_root=project_root(), entropy_home=home, interactive=False)
    factory.bootstrap()
    factory.runtime()
    factory.observability()
    factory.ui()
    factory.infrastructure()

    if fresh:
        DatabaseInstaller(factory.context).install()
    else:
        # An upgrade: keep the job history, apply new migrations.
        factory.context.migration_manager.migrate()
    return home
