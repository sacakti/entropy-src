"""
Add user preferences and background images.
"""

from __future__ import annotations

from pathlib import Path

from lib.migrations.base import BaseMigration
from lib.database.connection import DatabaseConnection
from lib.database.objects.background_images import BackgroundImagesTable
from lib.database.objects.user_preferences import UserPreferencesTable
from lib.database.seeders.background_images import BackgroundImagesSeeder


class WebUIMigration(BaseMigration):
    """
    Add user preferences and seed built-in background images.
    """

    VERSION = 6

    DESCRIPTION = "Add user preferences and background images."

    def upgrade(
        self,
        connection: DatabaseConnection,
    ) -> None:
        """Create preference tables and seed default backgrounds."""

        UserPreferencesTable().create(connection)

        BackgroundImagesTable().create(connection)

        assets_directory = (
            Path(__file__).resolve().parents[2]
            / "assets"
            / "backgrounds"
        )

        BackgroundImagesSeeder(assets_directory).seed(connection)
