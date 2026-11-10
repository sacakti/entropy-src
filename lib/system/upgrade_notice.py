"""
Tell everyone when Entropy is about to be upgraded or rolled back, through a Vision
broadcast, so they can save their work before the server restarts.

The warning goes out when the administrator starts the upgrade, naming the time it
begins (the administrator chooses how many minutes people get); pages count down to
it live. It is ended once the upgrade is over, whatever the outcome: by the server
that ran it, just before it restarts (the new version may not know the notice), and
at once when it fails or is cancelled. The new server ends a notice left behind by a
server that died. Nothing else is broadcast.

A notice is recorded with the upgrade job as {"id", "created_at"}: a rollback restores
the database from before the upgrade, so an id alone could name another broadcast.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from lib.database.connection import DatabaseConnection
from lib.vision.broadcasts import BroadcastStore

LOGGER = logging.getLogger("entropy.system")

# After the upgrade begins: long enough for it to finish. The notice expires by
# itself should the server never return.
UPGRADE_MINUTES = 60
SENDER = "Entropy"


def _zone(connection: DatabaseConnection) -> Any:
    """The installation's time zone (Administration -> Settings), else the server's."""

    from zoneinfo import ZoneInfo

    from lib.system.settings import SystemSettings
    from lib.system.timezone import server_timezone, valid_timezone

    name = SystemSettings(connection).get("general")["timezone"]
    return ZoneInfo(name if name and valid_timezone(name) else server_timezone())


def message_for(
    action: str,
    target: Optional[str],
    by: str,
    starts_at: Optional[datetime],
    zone: Any,
    minutes: int,
) -> str:
    what = "upgraded" if action == "upgrade" else "rolled back"
    version = f" to {target}" if target else ""
    if starts_at is None or minutes <= 0:
        return (
            f"Entropy is being {what}{version} by {by} and restarts in a few minutes."
            " Save your work now; pages may not answer for a moment."
        )
    at = starts_at.astimezone(zone).strftime("%H:%M")
    return (
        f"Entropy will be {what}{version} at {at} ({zone.key}), in {minutes} minute"
        f"{'' if minutes == 1 else 's'}, by {by}. Save your work before then: the server"
        " restarts and pages may not answer for a few minutes."
    )


def announce(
    connection: DatabaseConnection,
    action: str,
    target: Optional[str],
    by: str,
    starts_at: Optional[datetime] = None,
    minutes: int = 0,
) -> Optional[Dict[str, Any]]:
    """Warn everyone; the notice, or None when it could not be sent."""

    what = "Upgrade" if action == "upgrade" else "Rollback"
    try:
        text = message_for(action, target, by, starts_at, _zone(connection), minutes)
        broadcast = BroadcastStore(connection).create(
            text,
            "warning",
            SENDER,
            max(minutes, 0) + UPGRADE_MINUTES,
            # Pages count down to it live.
            countdown_to=starts_at if minutes > 0 else None,
            countdown_label=f"{what} to {target}" if target else what,
        )
    except Exception as error:  # noqa: BLE001 - an upgrade never waits on its notice
        LOGGER.warning("Unable to announce the %s: %s", action, error)
        return None
    return {"id": broadcast["id"], "created_at": broadcast["created_at"]}


def end(connection: DatabaseConnection, notice: Optional[Dict[str, Any]]) -> None:
    """Stop broadcasting the notice (only that one: same id and creation time)."""

    if not notice:
        return
    try:
        store = BroadcastStore(connection)
        row = store.connection.fetchone(
            "SELECT created_at FROM vision_broadcasts WHERE id = ?", (notice.get("id"),)
        )
        if row is not None and row["created_at"] == notice.get("created_at"):
            store.end(int(notice["id"]))
    except Exception as error:  # noqa: BLE001 - the notice is a courtesy
        LOGGER.warning("Unable to end the upgrade notice: %s", error)
