from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_PARENT = Path(__file__).resolve().parents[3] / "resources" / "plugins" / "builtin"

sys.path.insert(
    0,
    str(PLUGIN_PARENT),
)
