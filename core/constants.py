"""
Application constants.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LOG_DIR = PROJECT_ROOT / "logs"

REPORT_DIR = PROJECT_ROOT / "reports"

DATABASE_DIR = PROJECT_ROOT / "database"

DATABASE_FILE = DATABASE_DIR / "entropy.db"

RUNTIME_DIR = PROJECT_ROOT / "runtime"

PID_DIR = RUNTIME_DIR / "pid"

STATE_DIR = RUNTIME_DIR / "state"

LOCK_DIR = RUNTIME_DIR / "locks"

RELEASE_DIR = PROJECT_ROOT / "releases"

PLUGIN_DIR = PROJECT_ROOT / "plugins"

WORKFLOW_DIR = PROJECT_ROOT / "workflow"

CONFIG_FILE = PROJECT_ROOT / "entropy.json"