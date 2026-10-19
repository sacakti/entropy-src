"""
Add user notifications.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.objects.notifications import NotificationsTable
from lib.migrations.base import BaseMigration


class NotificationsMigration(BaseMigration):
    """
    Store notifications shown in the web notification center.
    """

    VERSION = 8

    DESCRIPTION = "Add user notifications."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """Create the notifications table."""

        NotificationsTable().create(connection)
