from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Extension:

    name: str

    version: str

    wheel: str

    installer: str

    installed_at: datetime

    python_tag: str

    platform_tag: str

    dist_info: str = ""

    entry_points: list[str] = field(
        default_factory=list,
    )


@dataclass(frozen=True)
class ExtensionManifest:

    name: str

    version: str

    source: str | None = None

    checksum: str | None = None

    installer: str = "offline"
