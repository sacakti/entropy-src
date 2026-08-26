"""
Plugin upgrade planning.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import PluginChange, PluginChangeType


@dataclass(frozen=True)
class PluginUpgradePlan:
    """
    Plan describing which plugin changes can be applied.
    """

    changes: tuple[PluginChange, ...]

    blocked: tuple[PluginChange, ...]

    @property
    def has_changes(self) -> bool:
        """
        Return True when there are changes available to apply.
        """

        return bool(self.changes)

    @property
    def has_blocked(self) -> bool:
        """
        Return True when one or more changes are blocked.
        """

        return bool(self.blocked)


class PluginUpgradePlanner:
    """
    Determines which detected plugin changes are allowed.

    The planner does not modify plugins and does not perform
    installations.
    """

    def plan(
        self,
        changes: list[PluginChange],
        *,
        force: bool = False,
    ) -> PluginUpgradePlan:
        """
        Build an upgrade plan.

        Parameters
        ----------
        changes:
            Changes detected by PluginChangeDetector.

        force:
            Allow plugin downgrades.

        Returns
        -------
        PluginUpgradePlan
            Changes that can be applied and changes that are blocked.
        """

        allowed: list[PluginChange] = []
        blocked: list[PluginChange] = []

        for change in changes:

            if change.change_type is PluginChangeType.DOWNGRADE:

                if force:

                    allowed.append(
                        change,
                    )

                else:

                    blocked.append(
                        change,
                    )

                continue

            allowed.append(
                change,
            )

        return PluginUpgradePlan(
            changes=tuple(
                allowed,
            ),
            blocked=tuple(
                blocked,
            ),
        )
