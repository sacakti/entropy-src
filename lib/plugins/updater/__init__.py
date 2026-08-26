"""
Plugin update support.
"""

from .detector import (
    PluginChangeDetector,
)
from .executor import (
    PluginUpgradeExecutor,
    PluginUpgradeResult,
)
from .model import (
    PluginChange,
    PluginChangeType,
)
from .planner import (
    PluginUpgradePlan,
    PluginUpgradePlanner,
)
from .source import (
    PluginSource,
    PluginSourceDiscovery,
)

__all__ = [
    "PluginChange",
    "PluginChangeDetector",
    "PluginChangeType",
    "PluginSource",
    "PluginSourceDiscovery",
    "PluginUpgradeExecutor",
    "PluginUpgradePlan",
    "PluginUpgradePlanner",
    "PluginUpgradeResult",
]
