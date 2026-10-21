"""
Plugins shipped with Entropy (resources/plugins of the application).

A new Entropy release can bring plugins that are not installed yet, or
newer versions of installed ones. They are never installed by themselves:
people who may install plugins are told (a notification, once per plugin
version) and choose in the Plugins page what to install or upgrade.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger("entropy.plugins")

NOTIFIED_KEY = "plugins.bundled_notified"
INSTALL_PERMISSION = "plugins.write"
# The web UI opens the update list from a notification with this source.
NOTIFICATION_SOURCE = "plugins:updates"


def bundled_source(context: Any) -> Optional[Path]:
    """The application's plugin folder, if there is one."""

    # The running application's own resources (in an installed Entropy the
    # project root is the application directory).
    try:
        source = Path(context.bootstrap.resources.plugins)
    except AttributeError:
        return None
    return source if source.is_dir() else None


def _item(change: Any) -> Dict[str, Any]:
    manifest = change.manifest
    return {
        "qualified_name": change.qualified_name,
        "kind": change.change_type.value,
        "installed_version": change.installed_version,
        "available_version": change.available_version,
        "display_name": manifest.display_name or manifest.name,
        "description": manifest.description or "",
    }


def available(context: Any) -> Dict[str, Any]:
    """
    Plugins of the application folder that are new or newer than installed.
    Downgrades are left out: an installed plugin newer than the bundled one
    stays as it is.
    """

    source = bundled_source(context)
    if source is None or context.plugin_manager is None:
        return {"items": [], "error": None}
    try:
        changes = context.plugin_manager.check_updates(source)
    except Exception as exc:  # noqa: BLE001 - one bad manifest must not hide the page
        LOGGER.warning("Checking bundled plugins failed: %s", exc)
        return {"items": [], "error": str(exc)}
    items = [_item(change) for change in changes if change.change_type.value in ("new", "upgrade")]
    return {"items": items, "error": None}


def changes_for(context: Any, names: List[str]) -> List[Any]:
    """The detected (new or upgrade) changes for these plugins."""

    source = bundled_source(context)
    if source is None:
        return []
    wanted = set(names)
    return [
        change
        for change in context.plugin_manager.check_updates(source)
        if change.qualified_name in wanted and change.change_type.value in ("new", "upgrade")
    ]


# ----------------------------------------------------------------------
# Notifications
# ----------------------------------------------------------------------


def _notified(connection: Any) -> List[str]:
    row = connection.fetchone("SELECT value FROM settings WHERE key = ?", (NOTIFIED_KEY,))
    try:
        value = json.loads(row["value"]) if row and row["value"] else []
    except ValueError:
        value = []
    return [str(item) for item in value] if isinstance(value, list) else []


def installers(connection: Any) -> List[int]:
    """Active users who may install plugins."""

    from lib.authorization.service import AuthorizationService

    service = AuthorizationService(connection)
    rows = connection.fetchall("SELECT id FROM users WHERE is_active = 1")
    return [row["id"] for row in rows if service.has_permission(row["id"], INSTALL_PERMISSION)]


def notify_installers(context: Any) -> int:
    """
    Tell the people who may install plugins about bundled plugins they have
    not heard about yet (each plugin version once). Returns how many.
    """

    from lib.database.objects.settings import SettingsTable
    from lib.database.repositories.notifications import notify_user

    items = available(context)["items"]
    connection = context.database_manager.connection
    SettingsTable().create(connection)
    known = _notified(connection)
    fresh = [
        item
        for item in items
        if f"{item['qualified_name']}@{item['available_version']}" not in known
    ]
    if not fresh:
        return 0

    new = [item for item in fresh if item["kind"] == "new"]
    upgrades = [item for item in fresh if item["kind"] == "upgrade"]
    parts = []
    if upgrades:
        parts.append(
            "Upgrades: "
            + ", ".join(
                "{} {} → {}".format(
                    item["qualified_name"], item["installed_version"], item["available_version"]
                )
                for item in upgrades[:5]
            )
            + (f" and {len(upgrades) - 5} more" if len(upgrades) > 5 else "")
            + "."
        )
    if new:
        parts.append(
            "New: "
            + ", ".join(item["qualified_name"] for item in new[:5])
            + (f" and {len(new) - 5} more" if len(new) > 5 else "")
            + "."
        )
    title = (
        f"{len(fresh)} plugin update{'s' if len(fresh) != 1 else ''} available"
        if upgrades
        else f"{len(fresh)} new plugin{'s' if len(fresh) != 1 else ''} available"
    )
    message = " ".join(parts) + " Review and install them in Plugins."
    for user_id in installers(connection):
        notify_user(context, user_id, title, message, "info", NOTIFICATION_SOURCE)

    with connection.transaction():
        connection.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (
                NOTIFIED_KEY,
                json.dumps(
                    sorted(
                        set(known)
                        | {
                            f"{item['qualified_name']}@{item['available_version']}"
                            for item in fresh
                        }
                    )
                ),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return len(fresh)
