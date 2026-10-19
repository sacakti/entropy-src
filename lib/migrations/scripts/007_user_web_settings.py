"""
Add profile pictures and web UI settings.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.objects.user_web_settings import (
    UserAvatarsTable,
    UserWebSettingsTable,
)
from lib.migrations.base import BaseMigration


class UserWebSettingsMigration(BaseMigration):
    """
    Store profile pictures and wallpaper placement and shuffle settings.
    """

    VERSION = 7

    DESCRIPTION = "Add profile pictures and web UI settings."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """Create the avatar and web settings tables."""

        UserAvatarsTable().create(connection)

        UserWebSettingsTable().create(connection)
