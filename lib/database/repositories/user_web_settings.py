"""
Profile picture and web UI settings repository.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Tuple

from lib.database.connection import DatabaseConnection
from lib.database.objects.user_web_settings import (
    UserAvatarsTable,
    UserWebSettingsTable,
)
from lib.database.repository import Repository


class UserWebSettingsRepository(Repository):
    """
    Profile pictures and free-form web UI settings, one record per user.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:
        super().__init__(connection)

        # Servers upgraded without `ent migrate` still get the tables;
        # both statements are CREATE TABLE IF NOT EXISTS.
        if not getattr(connection, "_entropy_web_settings_ready", False):
            with self.connection.transaction():
                UserAvatarsTable().create(connection)
                UserWebSettingsTable().create(connection)

            # Remembered on the connection: ids can be reused by new objects.
            setattr(connection, "_entropy_web_settings_ready", True)

    # ------------------------------------------------------------------
    # Avatar
    # ------------------------------------------------------------------

    def get_avatar(
        self,
        user_id: int,
    ) -> Optional[Tuple[str, bytes, str]]:
        """Return (mime type, bytes, updated at) or None."""

        row = self.fetchone(
            """
            SELECT mime_type, image_data, updated_at
            FROM user_avatars
            WHERE user_id = ?
            """,
            (user_id,),
        )

        if row is None:
            return None

        return row["mime_type"], bytes(row["image_data"]), row["updated_at"]

    def avatar_version(
        self,
        user_id: int,
    ) -> Optional[str]:
        """Return the avatar's update time, used to bust browser caches."""

        row = self.fetchone(
            "SELECT updated_at FROM user_avatars WHERE user_id = ?",
            (user_id,),
        )

        return row["updated_at"] if row else None

    def set_avatar(
        self,
        user_id: int,
        mime_type: str,
        data: bytes,
    ) -> None:

        with self.connection.transaction():
            self.execute(
                """
                INSERT INTO user_avatars (user_id, mime_type, image_data, updated_at)
                VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    mime_type = excluded.mime_type,
                    image_data = excluded.image_data,
                    updated_at = excluded.updated_at
                """,
                (user_id, mime_type, data),
            )

    def delete_avatar(
        self,
        user_id: int,
    ) -> None:

        with self.connection.transaction():
            self.execute(
                "DELETE FROM user_avatars WHERE user_id = ?",
                (user_id,),
            )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(
        self,
        user_id: int,
    ) -> dict[str, Any]:

        row = self.fetchone(
            "SELECT settings FROM user_web_settings WHERE user_id = ?",
            (user_id,),
        )

        if row is None:
            return {}

        try:
            value = json.loads(row["settings"])
        except ValueError:
            return {}

        return value if isinstance(value, dict) else {}

    def update_settings(
        self,
        user_id: int,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge top-level keys into the user's settings and return them."""

        with self.connection.transaction():
            settings = self.get_settings(user_id)
            settings.update(changes)

            self.execute(
                """
                INSERT INTO user_web_settings (user_id, settings, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    settings = excluded.settings,
                    updated_at = excluded.updated_at
                """,
                (user_id, json.dumps(settings)),
            )

        return settings
