"""
Application constants.
"""

from pathlib import Path
from typing import Literal

# ------------------------------------------------------------------
# Database migration constants
# ------------------------------------------------------------------

DATABASE_MIGRATION_PACKAGE = "lib.migrations.scripts"

# ------------------------------------------------------------------
# Linux Executor constants
# ------------------------------------------------------------------

SUPPORTED_ARCHIVES = {
    ".zip": "zip",
    ".tar": "tar",
    ".tar.gz": "gztar",
    ".tgz": "gztar",
    ".tar.bz2": "bztar",
    ".tbz2": "bztar",
    ".tar.xz": "xztar",
    ".txz": "xztar",
}

TarMode = Literal[
    "w",
    "w:gz",
    "w:bz2",
    "w:xz",
]

TAR_MODES: dict[str, TarMode] = {
    "tar": "w",
    "gztar": "w:gz",
    "bztar": "w:bz2",
    "xztar": "w:xz",
}

# ------------------------------------------------------------------
# Plugin constants
# ------------------------------------------------------------------

SEARCH_PATHS = (
    "plugins.custom",
    "plugins.builtin",
)

# ------------------------------------------------------------------
# Logger contants
# ------------------------------------------------------------------

CATEGORIES = (
    "system",
    "user",
    "auth",
    "cli",
    "workflow",
    "database",
    "shell",
    "oc",
    "plugin",
    "process",
    "report",
    "git",
)

LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "SUCCESS": 20,
    "WARNING": 30,
    "ERROR": 40,
    "EXCEPTION": 40,
    "CRITICAL": 50,
}

CONSOLE_LEVELS = {
    "NORMAL": 0,
    "VERBOSE": 1,
    "DEBUG": 2,
}

# ------------------------------------------------------------------
# Template constants
# ------------------------------------------------------------------


class PluginTemplates:
    """
    Plugin template paths.
    """

    INIT = "plugin/__init__.py.j2"
    MANIFEST = "plugin/plugin.json.j2"
    PLUGIN = "plugin/plugin.py.j2"
