from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_PARENT = (
    Path(__file__).resolve().parents[2] / "resources" / "plugins" / "custom" / "cache_refresh"
)

sys.path.insert(
    0,
    str(PLUGIN_PARENT),
)
