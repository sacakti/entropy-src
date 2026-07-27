"""
Application constants.
"""

from pathlib import Path

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RESOURCE_DIR = PROJECT_ROOT / "resources"

LOG_DIR = PROJECT_ROOT / "logs"

DATABASE_DIR = PROJECT_ROOT / "lib" / "database"

TEMPLATE_DIR = PROJECT_ROOT / "templates"

PLUGIN_DIR = PROJECT_ROOT / "plugins" 

DATABASE_FILE = DATABASE_DIR / "entropy.db"

RUNTIME_DIR = PROJECT_ROOT / "runtime"

PID_DIR = RUNTIME_DIR / "pid"

STATE_DIR = RUNTIME_DIR / "state"

LOCK_DIR = RUNTIME_DIR / "locks"

CONFIG_DIR = RESOURCE_DIR / "config"

RELEASE_DIR = RESOURCE_DIR / "releases"

WORKFLOW_DIR = RESOURCE_DIR / "workflows"

REPORT_DIR = RESOURCE_DIR / "reports"

CONFIG_FILE = CONFIG_DIR / "entropy.json"

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

TAR_MODES = {
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