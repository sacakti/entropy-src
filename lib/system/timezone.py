"""
The time zone Entropy shows times in.

People see times in their own zone (Settings -> Time zone), else in the
installation's zone (Administration -> Settings -> General), else in the
server's zone. Stored times stay UTC; only their display changes.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FALLBACK = "UTC"


def valid_timezone(name: str) -> bool:
    """Whether `name` is an IANA time zone this server knows, e.g. Europe/Berlin."""

    if not name or len(name) > 64 or name.startswith(("/", ".")) or ".." in name:
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _from_localtime(path: Path) -> Optional[str]:
    # /etc/localtime -> /usr/share/zoneinfo/Europe/Berlin
    try:
        target = str(path.resolve())
    except OSError:
        return None
    marker = "zoneinfo/"
    if marker not in target:
        return None
    name = target.split(marker, 1)[1]
    # posix/ and right/ hold the same zones with other leap second rules.
    for prefix in ("posix/", "right/"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    return name


def server_timezone() -> str:
    """The server's IANA time zone name; UTC when it cannot be told."""

    candidates = [os.environ.get("TZ", "").lstrip(":")]
    localtime = Path("/etc/localtime")
    if localtime.is_symlink():
        candidates.append(_from_localtime(localtime) or "")
    with contextlib.suppress(OSError):
        candidates.append(Path("/etc/timezone").read_text(encoding="utf-8").strip())
    for name in candidates:
        if name and valid_timezone(name):
            return name
    return FALLBACK
