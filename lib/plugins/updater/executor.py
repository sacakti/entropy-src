"""
Plugin upgrade execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from lib.models.plugin import Plugin

from ..installer import PluginInstaller
from .model import PluginChange, PluginChangeType
from .planner import PluginUpgradePlan


@dataclass(frozen=True)
class PluginUpgradeResult:
    """
    Result of a plugin upgrade operation.
    """

    upgraded: tuple[Plugin, ...]

    failed: tuple[PluginChange, ...]

    @property
    def success(self) -> bool:
        """
        Return True when all planned changes succeeded.
        """

        return not self.failed


class PluginUpgradeExecutor:
    """
    Executes plugin upgrade plans.

    Installation is delegated entirely to PluginInstaller.
    """

    def __init__(
        self,
        installer: PluginInstaller,
    ) -> None:

        self._installer = installer

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def execute(
        self,
        plan: PluginUpgradePlan,
    ) -> PluginUpgradeResult:
        """
        Execute a plugin upgrade plan.

        New plugins and upgrades are installed using the existing
        PluginInstaller. Downgrades are also passed to the installer
        when they have already been authorized by the planner.
        """

        upgraded: list[Plugin] = []
        failed: list[PluginChange] = []

        for change in plan.changes:

            try:

                plugin = self._install(
                    change,
                )

            except Exception:

                failed.append(
                    change,
                )

                continue

            upgraded.append(
                plugin,
            )

        return PluginUpgradeResult(
            upgraded=tuple(
                upgraded,
            ),
            failed=tuple(
                failed,
            ),
        )

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def _install(
        self,
        change: PluginChange,
    ) -> Plugin:
        """
        Install one plugin change.
        """

        reinstall = change.change_type is not PluginChangeType.NEW

        return self._installer.install(
            change.source,
            reinstall=reinstall,
        )
