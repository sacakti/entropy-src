"""
User preferences table.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class UserPreferencesTable(DatabaseObject):

    NAME = "user_preferences"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences
            (
                user_id              INTEGER PRIMARY KEY,
                theme                TEXT NOT NULL DEFAULT 'dark',
                accent_color         TEXT NOT NULL DEFAULT '#d7ff63',
                background_image_id  INTEGER,

                background_fit       TEXT NOT NULL DEFAULT 'cover'
                    CHECK (background_fit IN ('cover', 'contain', 'fill')),

                background_opacity   INTEGER NOT NULL DEFAULT 35
                    CHECK (background_opacity BETWEEN 0 AND 100),

                created_at            TEXT NOT NULL,
                updated_at            TEXT NOT NULL,

                FOREIGN KEY (user_id)
                    REFERENCES users(id),

                CHECK (theme IN ('dark', 'light'))
            )
            """
        )
