from __future__ import annotations

import sys
from pathlib import Path

# The plugin imports its required plugin as `sqlplus.generic`, the package
# name the loader gives it; make it importable the same way.
PLUGINS_ROOT = Path(__file__).resolve().parents[3] / "resources" / "plugins"

sys.path.insert(
    0,
    str(PLUGINS_ROOT),
)
