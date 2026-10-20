"""
The installation record: how this Entropy was installed, so upgrades and
the web server manager can repeat the same choices.

Stored at <Entropy home>/config/install.json.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def entropy_home() -> Path:
    return Path(os.environ.get("ENTROPY_HOME") or Path.home() / ".entropy")


def application_root() -> Path:
    return Path(__file__).resolve().parents[2]


def record_path(home: Path | None = None) -> Path:
    return (home or entropy_home()) / "config" / "install.json"


def load(home: Path | None = None) -> Dict[str, Any]:
    """The installation record; defaults for source checkouts."""

    record: Dict[str, Any] = {}
    with contextlib.suppress(OSError, ValueError):
        record = json.loads(record_path(home).read_text(encoding="utf-8"))

    record.setdefault("python", sys.executable)
    record.setdefault("deps", "bundled")
    record.setdefault("index_url", None)
    record.setdefault("platform", None)
    record.setdefault("application", str(application_root()))
    web = record.setdefault("web", {})
    web.setdefault("host", DEFAULT_HOST)
    web.setdefault("port", DEFAULT_PORT)
    web.setdefault("service", "process")
    record.setdefault("upgrades", [])
    return record


def scratch_directory(project_root: Path | str) -> Path:
    """Worker logs and run definitions: <application>/tmp, or ENTROPY_TMP
    when the application directory is read-only (the container image)."""

    configured = os.environ.get("ENTROPY_TMP")
    return Path(configured) if configured else Path(project_root) / "tmp"


def in_container() -> bool:
    """Running from the container image: upgrades come from a new image."""

    return os.environ.get("ENTROPY_CONTAINER", "").strip().lower() in ("1", "true", "yes", "on")


def theme_enabled(home: Path | None = None) -> bool:
    """Wallpaper customization (backgrounds, opacity, backdrop, shuffle).

    Off unless ENTROPY_THEME_ENABLE=1 was set for ./install (kept in the
    installation record); the variable also overrides it at runtime.
    """

    configured = os.environ.get("ENTROPY_THEME_ENABLE")
    if configured is not None:
        return configured.strip().lower() in ("1", "true", "yes", "on")
    return bool(load(home).get("features", {}).get("theme", False))


def save(record: Dict[str, Any], home: Path | None = None) -> None:
    path = record_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
