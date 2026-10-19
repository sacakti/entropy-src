"""
Browser profile pictures and web UI settings tables.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class UserAvatarsTable(DatabaseObject):

    NAME = "user_avatars"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_avatars
            (
                user_id     INTEGER PRIMARY KEY,
                mime_type   TEXT NOT NULL,
                image_data  BLOB NOT NULL,
                updated_at  TEXT NOT NULL,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
            )
            """
        )


class UserWebSettingsTable(DatabaseObject):

    NAME = "user_web_settings"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_web_settings
            (
                user_id     INTEGER PRIMARY KEY,
                settings    TEXT NOT NULL DEFAULT '{}',
                updated_at  TEXT NOT NULL,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
            )
            """
        )
