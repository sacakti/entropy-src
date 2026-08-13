"""
Application constants.
"""

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
# Template constants
# ------------------------------------------------------------------

PLUGIN_MANIFEST = "plugin.json"
PLUGIN_FILES = (
        ("plugin/__init__.py.j2", "__init__.py"),
        ("plugin/plugin.py.j2", "plugin.py"),
        ("plugin/plugin.json.j2", "plugin.json"),
        ("plugin/README.md.j2", "README.md"),
        ("plugin/MAN.md.j2", "MAN.md"),
        ("plugin/workflow.json.j2", "workflow.json"),
        ("plugin/requirements.txt.j2", "requirements.txt"),
    )

PLUGIN_DIRECTORIES = ("migrations",)

# Workflow
DEFAULT_SEPARATOR = ";"
