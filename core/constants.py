"""
Application constants.
"""

from pathlib import Path

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

APPLICATION_ROOT = PROJECT_ROOT / "entropy.py"

ENTROPY_HOME = Path.home() / ".entropy"

RESOURCE_DIR = PROJECT_ROOT / "resources"

LOG_DIR = PROJECT_ROOT / "logs"

TEMPLATE_DIR = PROJECT_ROOT / "templates"

DEFAULT_CONFIG_FILE = PROJECT_ROOT / "lib" / "install" / "entropy.json.config"

RELEASE_DIR = RESOURCE_DIR / "releases"

WORKFLOW_DIR = RESOURCE_DIR / "workflows"

REPORT_DIR = RESOURCE_DIR / "reports"

PLUGIN_DIR = RESOURCE_DIR / "plugins"

CONFIG_DIR = ENTROPY_HOME / "config"

RUNTIME_DIR = ENTROPY_HOME / "runtime"

PACKAGE_DIR = ENTROPY_HOME / "site-packages"

DATABASE_DIR = ENTROPY_HOME / "database"

SESSION_DIRECTORY = ENTROPY_HOME / "sessions"

SESSION_FILE = SESSION_DIRECTORY / "current.json"

DATABASE_FILE = DATABASE_DIR / "entropy.db"

CONFIG_FILE = CONFIG_DIR / "entropy.json"

PID_DIR = RUNTIME_DIR / "pid"

STATE_DIR = RUNTIME_DIR / "state"

LOCK_DIR = RUNTIME_DIR / "locks"

# ------------------------------------------------------------------
# Wheels constants
# ------------------------------------------------------------------
VENDOR_DIR = PROJECT_ROOT / "core" / "vendor"
REQUIREMENT_FILE =  VENDOR_DIR / "requirements.txt"
LAUNCHER_DIR_WIN = Path.home() / "AppData" / "Local" / "Programs" / "Entropy" / "ent.cmd"
LAUNCHER_DIR_UNIX = Path.home() / ".local" / "bin" / "ent"

# ------------------------------------------------------------------
# Database migration constants
# ------------------------------------------------------------------

DATABASE_MIGRATION_PACKAGE = (
    "lib.database.migrations"
)

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